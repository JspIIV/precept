"""The moderation rules, exercised through the real contract methods.

precept.py is loaded against a stub of the runtime, a real Precept is built, and the
assertions go through open_space(), post(), report() and appeal(). The stub controls
the two things the contract cannot: the page the round fetches and the verdict it
returns. It proves the rule judged is the space's own, that only a VIOLATES removes a
post, that an unrelated or unreadable page never does, that only the author can appeal,
that an appeal which reads ALLOWED restores the post and corrects the record, and that
history is preserved.

    python tests/precept_rules.py
"""

import io
import json
import os
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
CONTRACT = os.path.join(HERE, "..", "contracts", "precept.py")


class _Store:
    def __init__(self, kind): self.kind = kind
    def __class_getitem__(cls, item): return cls("map" if isinstance(item, tuple) else "list")
    def make(self): return {} if self.kind == "map" else []


class _Address:
    def __init__(self, hex_value): self.as_hex = hex_value
    def __str__(self): return str(self.as_hex)


class _Message:
    def __init__(self):
        self.sender_address = _Address("0x" + "0" * 40)
        self.value = 0


class _Web:
    def __init__(self):
        self.page = "a post"

    def render(self, url):
        if self.page is None:
            raise RuntimeError("could not fetch")
        return self.page


class _Nondet:
    def __init__(self, web):
        self.web = web
        self.last_prompt = None
        self.answer = "{}"

    def exec_prompt(self, task):
        self.last_prompt = task
        return self.answer


class _Write:
    def __call__(self, fn): return fn
    def payable(self, fn): return fn


class _PublicNS:
    def __init__(self):
        self.write = _Write()
        self.view = lambda fn: fn


class _EqPrinciple:
    def prompt_comparative(self, run, principle=None): return run()


class _GL:
    def __init__(self):
        self.Contract = object
        self.public = _PublicNS()
        self.message = _Message()
        self.nondet = _Nondet(_Web())
        self.eq_principle = _EqPrinciple()


def load():
    gl = _GL()
    fake = types.ModuleType("genlayer")
    fake.gl = gl
    fake.DynArray = _Store
    fake.TreeMap = _Store
    fake.u32 = int
    fake.u256 = int
    fake.Address = _Address
    sys.modules["genlayer"] = fake
    module = types.ModuleType("precept_under_test")
    exec(compile(io.open(CONTRACT, encoding="utf-8").read(), CONTRACT, "exec"), module.__dict__)
    return module, gl


def fresh(module):
    contract = module.Precept.__new__(module.Precept)
    for field, declared in module.Precept.__annotations__.items():
        setattr(contract, field, declared.make())
    contract.__init__()
    return contract


RESULTS = []


def check_(label, condition):
    RESULTS.append((label, bool(condition)))
    print(("  ok  " if condition else " FAIL "), label)


MOD = "0x1111111111111111111111111111111111111111"
AUTHOR = "0x2222222222222222222222222222222222222222"
OTHER = "0x3333333333333333333333333333333333333333"

URL = "https://example.org/post"
RULE = "No advertising, promotional offers, or solicitations; on-topic discussion only."


def answer(verdict, reason="r", quote="q"):
    return json.dumps({"verdict": verdict, "reason": reason, "quote": quote})


def main():
    module, gl = load()

    def as_(address): gl.message.sender_address = _Address(address)

    print("the pure outcome rules")
    check_("VIOLATES removes on a report", module._report_outcome("VIOLATES") == "REMOVE")
    check_("ALLOWED keeps on a report", module._report_outcome("ALLOWED") == "KEEP")
    check_("UNCLEAR is a no-op on a report", module._report_outcome("UNCLEAR") == "NOOP")
    check_("ALLOWED restores on an appeal", module._appeal_outcome("ALLOWED") == "RESTORE")
    check_("VIOLATES upholds on an appeal", module._appeal_outcome("VIOLATES") == "UPHOLD")
    check_("UNCLEAR is a no-op on an appeal", module._appeal_outcome("UNCLEAR") == "NOOP")

    print("\nopening a space and posting")
    c = fresh(module)
    as_(MOD)
    sp = json.loads(c.open_space("Town Square", RULE))
    sid = sp["id"]
    check_("a space opens with its rule", sp["ok"])
    check_("posting to a missing space is refused", not json.loads(c.post("999", URL))["ok"])
    as_(AUTHOR)
    spam = json.loads(c.post(sid, URL))["id"]
    ontopic = json.loads(c.post(sid, URL + "/2"))["id"]
    check_("the author's record counts the posts", json.loads(c.record(AUTHOR)) ==
           {"exists": True, "address": AUTHOR, "posts": 2, "removed": 0})

    print("\na report is judged against the space's own rule")
    as_(OTHER)
    gl.nondet.answer = answer("VIOLATES", reason="an ad", quote="BUY NOW")
    rep = json.loads(c.report(spam))
    check_("a violating post is REMOVED", rep["outcome"] == "REMOVE" and json.loads(c.item(spam))["status"] == "REMOVED")
    check_("the space's rule was put in front of the round", RULE in gl.nondet.last_prompt)
    check_("the author's record shows one removed", json.loads(c.record(AUTHOR))["removed"] == 1)

    print("\nan allowed post is not removed")
    gl.nondet.answer = answer("ALLOWED", reason="on topic")
    rep2 = json.loads(c.report(ontopic))
    check_("an allowed post stays LISTED", rep2["outcome"] == "KEEP" and json.loads(c.item(ontopic))["status"] == "LISTED")
    check_("no reputation moved for an allowed post", json.loads(c.record(AUTHOR))["removed"] == 1)

    print("\nonly the author can appeal, and only a removed post")
    check_("a listed post cannot be appealed", not json.loads(c.appeal(ontopic))["ok"])
    as_(OTHER)
    check_("a non-author cannot appeal a removed post", not json.loads(c.appeal(spam))["ok"])

    print("\nan appeal that reads ALLOWED restores the post and corrects the record")
    as_(AUTHOR)
    gl.nondet.answer = answer("ALLOWED", reason="on second read it fits the rule")
    ap = json.loads(c.appeal(spam))
    check_("a successful appeal RESTORES the post to LISTED", ap["outcome"] == "RESTORE" and json.loads(c.item(spam))["status"] == "LISTED")
    check_("the restore corrects the author's removed count back to zero", json.loads(c.record(AUTHOR))["removed"] == 0)

    print("\nan appeal that still reads VIOLATES upholds the removal")
    gl.nondet.answer = answer("VIOLATES", reason="still an ad")
    c.report(spam)  # remove it again
    as_(AUTHOR)
    gl.nondet.answer = answer("VIOLATES", reason="upheld")
    ap2 = json.loads(c.appeal(spam))
    check_("an upheld appeal leaves the post REMOVED", ap2["outcome"] == "UPHOLD" and json.loads(c.item(spam))["status"] == "REMOVED")

    print("\nunreadable and not-found pages never remove a post")
    as_(AUTHOR)
    clean = json.loads(c.post(sid, URL + "/3"))["id"]
    as_(OTHER)
    gl.nondet.web.page = None
    unread = json.loads(c.report(clean))
    check_("an unreadable post is UNCLEAR and stays LISTED", unread["verdict"] == "UNCLEAR" and json.loads(c.item(clean))["status"] == "LISTED")
    gl.nondet.web.page = "404: Not Found"
    nf = json.loads(c.report(clean))
    check_("a not-found body is UNCLEAR and stays LISTED", nf["verdict"] == "UNCLEAR" and json.loads(c.item(clean))["status"] == "LISTED")

    print("\nhistory is preserved across every report and appeal")
    hist = json.loads(c.history(spam))
    kinds = [e["kind"] + ":" + e["verdict"] for e in hist["log"]]
    check_("the spam post's full log is kept, oldest first",
           kinds == ["report:VIOLATES", "appeal:ALLOWED", "report:VIOLATES", "appeal:VIOLATES"])

    print("\nthe book counts listed and removed")
    size = json.loads(c.size())
    check_("one space, and the posts split between listed and removed",
           size["spaces"] == 1 and size["removed"] == 1 and size["listed"] == 2)

    failed = [label for label, ok in RESULTS if not ok]
    print()
    if failed:
        print("%d of %d checks failed" % (len(failed), len(RESULTS)))
        return 1
    print("%d checks, all through open_space(), post(), report() and appeal() on a real Precept"
          % len(RESULTS))
    return 0


if __name__ == "__main__":
    sys.exit(main())
