# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
"""Precept: content moderation by one public rule, the same for everyone, with an auditable appeal.

Most moderation is a black box. A post disappears and nobody outside the room knows
which rule it broke, whether the rule was applied evenly, or how to contest it. Precept
turns the rule into the contract. A space is opened with one rule in plain words. Anyone
may post content into it, and anyone may report a post. The contract fetches the post
itself and a round of GenLayer validators reads it against that one published rule and
decides whether it violates it. The rule is the space's, not the reporter's, so the same
standard is applied to everyone and no one can attach a rule of convenience to remove a
post they dislike.

A removal is not the end of the story. The author of a removed post can appeal, and a
fresh round reads the post against the same rule again; if it now reads as within the
rule, the post is restored. Every report and every appeal is kept, append-only, on the
post: who raised it, the verdict, and the passage the round cited. Moderation here has a
public rule, an even hand, and a paper trail.

## What it settles

    VIOLATES   the post breaks the space's rule -> it is REMOVED
    ALLOWED    the post is within the rule -> the report is dismissed, the post stays LISTED
    UNCLEAR    the post could not be read, or does not settle it: nothing changes

Only VIOLATES removes a post; an unrelated or unreadable page never does. An appeal that
reads ALLOWED restores the post and corrects the author's record.

## What it refuses

The rule is fixed to the space and copied onto each post when it is filed, so the round
always judges against the rule that was in force, and a reporter cannot supply their own.
Only the author of a removed post may appeal it. An unreadable post is UNCLEAR and changes
nothing. Every actor is bound to the caller, and history is preserved, never overwritten.

## Where it stops, plainly

It judges a post against a rule in words, which is a judgement, not a proof: name a rule
a stranger could apply the same way twice, and a post a third party controls. It records a
standing and a history, not a punishment; what a removal costs is left to the space.
"""

from genlayer import *
import json

VIOLATES = "VIOLATES"
ALLOWED = "ALLOWED"
UNCLEAR = "UNCLEAR"
VERDICTS = (VIOLATES, ALLOWED, UNCLEAR)

LISTED = "LISTED"
REMOVED = "REMOVED"

MAX_RULE = 400
MAX_NAME = 120
MAX_URL = 300
MAX_PAGE = 6000
MAX_REASON = 300
MAX_QUOTE = 300
MAX_LOG = 60

FETCH_FAILED = "__FETCH_FAILED__"


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def _clip(text: str, limit: int) -> str:
    text = str(text).strip()
    return text if len(text) <= limit else text[:limit] + " [...]"


def _whole(value) -> int:
    try:
        return int(str(value).strip())
    except Exception:
        return -1


def _addr(value) -> str:
    text = str(value).strip().lower()
    if not text.startswith("0x") or len(text) != 42:
        return ""
    for character in text[2:]:
        if character not in "0123456789abcdef":
            return ""
    return text


def _url_ok(url: str) -> bool:
    text = str(url).strip()
    if len(text) < 8 or len(text) > MAX_URL or " " in text:
        return False
    return text.startswith("https://") or text.startswith("http://")


def _report_outcome(verdict: str) -> str:
    """A report's effect on a LISTED post. Only VIOLATES removes it."""
    if verdict == VIOLATES:
        return "REMOVE"
    if verdict == ALLOWED:
        return "KEEP"
    return "NOOP"


def _appeal_outcome(verdict: str) -> str:
    """An appeal's effect on a REMOVED post. Only ALLOWED restores it."""
    if verdict == ALLOWED:
        return "RESTORE"
    if verdict == VIOLATES:
        return "UPHOLD"
    return "NOOP"


def _field(raw: str, name: str, allowed, fallback: str) -> str:
    try:
        text = str(raw).strip()
        obj = json.loads(text[text.index("{"):text.rindex("}") + 1])
        if isinstance(obj, dict):
            said = str(obj.get(name, "")).strip().upper()
            return said if said in allowed else fallback
    except Exception:
        pass
    return fallback


def _text_field(raw: str, name: str, limit: int) -> str:
    try:
        text = str(raw).strip()
        obj = json.loads(text[text.index("{"):text.rindex("}") + 1])
        if isinstance(obj, dict):
            return _clip(str(obj.get(name, "")), limit)
    except Exception:
        pass
    return ""


def _fetch(url: str) -> str:
    try:
        got = gl.nondet.web.render(url)
        page = got if isinstance(got, str) else getattr(got, "body", "")
        if isinstance(page, (bytes, bytearray)):
            page = page.decode("utf-8", "replace")
        page = _clip(str(page), MAX_PAGE)
        if not page:
            return FETCH_FAILED
        if page.strip().lower().startswith(("404: not found", "404 not found", "not found")):
            return FETCH_FAILED
        return page
    except Exception:
        return FETCH_FAILED


def _task(rule: str, content: str) -> str:
    return f"""A space publishes one rule, and every post in it is judged against that same rule.
Read the post below and decide whether it breaks the rule.

THE RULE OF THE SPACE:
{rule}

THE POST:
{content}

Decide one of:
  {VIOLATES} the post breaks the rule
  {ALLOWED} the post was read and does not break the rule (disagreement or criticism that
    the rule permits is {ALLOWED}, not a violation)
  {UNCLEAR} the post could not be read, or there is not enough to tell whether it breaks the rule

Apply the rule as written, evenly, to what the post actually says. A page that is an error
page, a "404" or "not found" notice, an empty page, or a page unrelated to any post is not a
post you can judge: that is {UNCLEAR}, never {VIOLATES}. Do not invent rules the space did not
state.

Reply with bare JSON and nothing else:
{{"verdict": "{VIOLATES}" or "{ALLOWED}" or "{UNCLEAR}",
  "quote": "the passage that decided it, or empty",
  "reason": "one sentence naming what decided it against the rule"}}"""


class Precept(gl.Contract):
    """Spaces with one public rule; posts judged against it, removable and restorable, with a full log."""

    # str(id) -> space as JSON.
    spaces: TreeMap[str, str]
    space_ids: DynArray[str]
    # str(id) -> post as JSON, including its append-only moderation log.
    items: TreeMap[str, str]
    item_ids: DynArray[str]
    # address -> {"posts": n, "removed": n} as JSON.
    records: TreeMap[str, str]

    def __init__(self) -> None:
        pass

    def _bump(self, who: str, posts_delta: int, removed_delta: int) -> None:
        raw = self.records.get(who, None)
        rec = json.loads(raw) if raw is not None else {"posts": 0, "removed": 0}
        rec["posts"] = int(rec.get("posts", 0)) + posts_delta
        rec["removed"] = int(rec.get("removed", 0)) + removed_delta
        self.records[who] = json.dumps(rec)

    @gl.public.write
    def open_space(self, name: str, rule: str) -> str:
        """Open a moderated space with one rule in plain words. Bound to the caller (the moderator)."""
        moderator = gl.message.sender_address.as_hex.lower()
        nm = _clip(name, MAX_NAME)
        rl = _clip(rule, MAX_RULE)
        if not nm:
            return json.dumps({"ok": False, "error": "give the space a name"})
        if len(rl) < 8:
            return json.dumps({"ok": False, "error": "state the rule in plain words"})
        sid = str(len(self.space_ids))
        self.spaces[sid] = json.dumps({"id": sid, "moderator": moderator, "name": nm, "rule": rl,
                                       "opened_at": _now_iso()})
        self.space_ids.append(sid)
        return json.dumps({"ok": True, "id": sid, "rule": rl})

    @gl.public.write
    def post(self, space_id: str, content_url: str) -> str:
        """Post content into a space. Bound to the caller (the author). It starts LISTED.

        The space's rule is copied onto the post now, so it will always be judged against
        the rule that was in force when it was filed.
        """
        author = gl.message.sender_address.as_hex.lower()
        sid = str(space_id).strip()
        link = str(content_url).strip()
        stored = self.spaces.get(sid, None)
        if stored is None:
            return json.dumps({"ok": False, "error": "no space with that id"})
        if not _url_ok(link):
            return json.dumps({"ok": False, "error": "give an http(s) URL for the content"})
        rule = json.loads(stored)["rule"]

        pid = str(len(self.item_ids))
        record = {
            "id": pid,
            "space_id": sid,
            "author": author,
            "content_url": link,
            "rule": rule,
            "status": LISTED,
            "posted_at": _now_iso(),
            "reports": 0,
            "appeals": 0,
            "last_verdict": "",
            "reason": "",
            "quote": "",
            "log": [],
        }
        self.items[pid] = json.dumps(record)
        self.item_ids.append(pid)
        self._bump(author, 1, 0)
        return json.dumps({"ok": True, "id": pid, "status": LISTED})

    def _judge(self, content_url: str, rule: str) -> str:
        # Copy into locals before the round. Nothing inside the block reads self
        # and nothing inside it raises.
        url = content_url
        rl = rule

        def look() -> str:
            page = _fetch(url)
            if page == FETCH_FAILED:
                return json.dumps({"verdict": UNCLEAR, "quote": "",
                                   "reason": "the post could not be read"})
            try:
                return str(gl.nondet.exec_prompt(_task(rl, page)))
            except Exception as error:
                return json.dumps({"verdict": UNCLEAR, "quote": "",
                                   "reason": _clip("the prompt failed: " + str(error), MAX_REASON)})

        return gl.eq_principle.prompt_comparative(
            look,
            principle=(
                f"Both answers must carry the same value in the field named verdict, one of "
                f"{VIOLATES}, {ALLOWED} or {UNCLEAR}. That single field decides whether a post is "
                "removed from a space, so two readers differing on it disagree about whether the post "
                "breaks the rule, not about how to word a judgement. The other fields are not compared, "
                "and the two readers will not have fetched byte-identical copies of the page."
            ),
        )

    @gl.public.write
    def report(self, item_id: str) -> str:
        """Report a listed post; the contract judges it against the space's rule. Open to anybody.

        VIOLATES removes the post and marks the author's record; ALLOWED dismisses the
        report and the post stays listed; UNCLEAR changes nothing.
        """
        reporter = gl.message.sender_address.as_hex.lower()
        pid = str(item_id).strip()
        stored = self.items.get(pid, None)
        if stored is None:
            return json.dumps({"ok": False, "error": "no post with that id"})
        record = json.loads(stored)
        if record["status"] != LISTED:
            return json.dumps({"ok": False, "error": "only a listed post can be reported",
                               "status": record["status"]})

        raw = self._judge(record["content_url"], record["rule"])
        verdict = _field(raw, "verdict", VERDICTS, "")
        if not verdict:
            return json.dumps({"ok": False, "error": "the round produced no verdict this contract recognises",
                               "round_said": _clip(str(raw), 400)})
        reason = _text_field(raw, "reason", MAX_REASON)
        quote = _text_field(raw, "quote", MAX_QUOTE)
        outcome = _report_outcome(verdict)

        record["reports"] = int(record.get("reports", 0)) + 1
        record["last_verdict"] = verdict
        record["reason"] = reason
        record["quote"] = quote
        log = list(record.get("log", []))
        log.append({"kind": "report", "at": _now_iso(), "by": reporter, "verdict": verdict,
                    "outcome": outcome, "quote": quote, "reason": reason})
        if len(log) > MAX_LOG:
            log = log[-MAX_LOG:]
        record["log"] = log
        if outcome == "REMOVE":
            record["status"] = REMOVED
            self._bump(record["author"], 0, 1)
        self.items[pid] = json.dumps(record)
        return json.dumps({"ok": True, "id": pid, "verdict": verdict, "outcome": outcome,
                           "status": record["status"], "reason": reason})

    @gl.public.write
    def appeal(self, item_id: str) -> str:
        """Appeal a removed post. Only the author may appeal; a fresh round re-reads it against the same rule."""
        who = gl.message.sender_address.as_hex.lower()
        pid = str(item_id).strip()
        stored = self.items.get(pid, None)
        if stored is None:
            return json.dumps({"ok": False, "error": "no post with that id"})
        record = json.loads(stored)
        if record["status"] != REMOVED:
            return json.dumps({"ok": False, "error": "only a removed post can be appealed",
                               "status": record["status"]})
        if who != record["author"]:
            return json.dumps({"ok": False, "error": "only the author of the post may appeal it"})

        raw = self._judge(record["content_url"], record["rule"])
        verdict = _field(raw, "verdict", VERDICTS, "")
        if not verdict:
            return json.dumps({"ok": False, "error": "the round produced no verdict this contract recognises",
                               "round_said": _clip(str(raw), 400)})
        reason = _text_field(raw, "reason", MAX_REASON)
        quote = _text_field(raw, "quote", MAX_QUOTE)
        outcome = _appeal_outcome(verdict)

        record["appeals"] = int(record.get("appeals", 0)) + 1
        record["last_verdict"] = verdict
        record["reason"] = reason
        record["quote"] = quote
        log = list(record.get("log", []))
        log.append({"kind": "appeal", "at": _now_iso(), "by": who, "verdict": verdict,
                    "outcome": outcome, "quote": quote, "reason": reason})
        if len(log) > MAX_LOG:
            log = log[-MAX_LOG:]
        record["log"] = log
        if outcome == "RESTORE":
            record["status"] = LISTED
            self._bump(record["author"], 0, -1)  # correct the record: the removal is undone
        self.items[pid] = json.dumps(record)
        return json.dumps({"ok": True, "id": pid, "verdict": verdict, "outcome": outcome,
                           "status": record["status"], "reason": reason})

    # ------------------------------------------------------------------ reads

    @gl.public.view
    def record(self, address: str) -> str:
        """An author's standing in the registry: posts made, and posts currently removed."""
        a = _addr(address)
        if not a:
            return json.dumps({"exists": False, "posts": 0, "removed": 0})
        raw = self.records.get(a, None)
        if raw is None:
            return json.dumps({"exists": False, "address": a, "posts": 0, "removed": 0})
        rec = json.loads(raw)
        return json.dumps({"exists": True, "address": a,
                           "posts": int(rec.get("posts", 0)), "removed": int(rec.get("removed", 0))})

    @gl.public.view
    def space(self, space_id: str) -> str:
        """A space and its rule."""
        sid = str(space_id).strip()
        stored = self.spaces.get(sid, None)
        if stored is None:
            return json.dumps({"exists": False})
        return stored

    @gl.public.view
    def item(self, item_id: str) -> str:
        """A post, including its full moderation log."""
        pid = str(item_id).strip()
        stored = self.items.get(pid, None)
        if stored is None:
            return json.dumps({"exists": False})
        return stored

    @gl.public.view
    def history(self, item_id: str) -> str:
        """The append-only log of every report and appeal against a post."""
        pid = str(item_id).strip()
        stored = self.items.get(pid, None)
        if stored is None:
            return json.dumps({"exists": False})
        record = json.loads(stored)
        return json.dumps({"exists": True, "id": pid, "status": record["status"],
                           "reports": record["reports"], "appeals": record["appeals"],
                           "log": record.get("log", [])})

    @gl.public.view
    def size(self) -> str:
        """How many spaces exist, and how many posts are listed and removed."""
        listed = 0
        removed = 0
        for position in range(len(self.item_ids)):
            state = json.loads(self.items[self.item_ids[position]])["status"]
            if state == LISTED:
                listed += 1
            elif state == REMOVED:
                removed += 1
        return json.dumps({"spaces": len(self.space_ids), "posts": len(self.item_ids),
                           "listed": listed, "removed": removed})

    @gl.public.view
    def page(self, start: str, count: str) -> str:
        """A slice of the posts, newest first, for a frontend to render."""
        total = len(self.item_ids)
        begin = _whole(start)
        want = _whole(count)
        if begin < 0:
            begin = 0
        if want < 1:
            want = 20
        if want > 50:
            want = 50
        out = []
        seen = 0
        position = total - 1 - begin
        while position >= 0 and seen < want:
            record = json.loads(self.items[self.item_ids[position]])
            record["log_count"] = len(record.get("log", []))
            record.pop("log", None)
            out.append(record)
            position -= 1
            seen += 1
        return json.dumps({"total": total, "start": begin, "count": len(out), "items": out})
