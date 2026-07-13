# NyxScript Cookbook

Practical, runnable scripts combining several
[standard library](NyxScript-Standard-Library-Reference) modules at
once. Every script on this page was actually run against a real target
before being written down here — copy-paste them and adjust the target
list.

## Batch-audit a list of domains, export a CSV summary

```
import "lib/csv.nyx" as csv
import "lib/math.nyx" as math
import "lib/validate.nyx" as validate

set targets = ["example.com", "openai.com"]
set good_targets = filter(targets, lambda(t): validate.is_valid_domain(t))

set rows = [["target", "finding_count"]]
set counts = []

foreach target in good_targets:
    run audit target as results
    set total = 0
    foreach r in results:
        set total = total + len(r.findings)
    end
    set rows = rows + [[target, str(total)]]
    set counts = counts + [total]
end

print csv.to_csv(rows)
print "average findings per target: " + str(math.mean(counts))
```

Swap `print csv.to_csv(rows)` for `save rows to "summary.csv"`... except
`save` only accepts scan-result lists, not arbitrary rows — write the
CSV text to a file with a plain script instead if you need it on disk:
combine this with `ui.status`/redirect the script's own output, or add a
small `write_text`-style plugin if you do this often (see
[Plugin Development](Plugin-Development)).

## Detect whether anything changed since last time

```
import "lib/hash.nyx" as hash

# In a real script, load previous_hash from wherever you stored it
# last run (a file, `nyx trends`, etc.) — this is illustrative.
set previous_hash = sha256(to_json(["a", "b", "c"]))

run dns "example.com" as current
set current_hash = sha256(to_json(current.findings))

if hash.has_changed(previous_hash, to_json(current.findings)):
    print "DNS posture changed since last check"
else:
    print "no change"
end
```

For a real change-tracking workflow across process runs (not just
within one script), `nyx watch` and `nyx trends` already do this —
reach for NyxScript's `hash.has_changed` when you need custom logic
`nyx watch --narrate` doesn't cover, like diffing something other than
the score.

## Retry with exponential backoff

```
import "lib/time.nyx" as time

set attempt = 0
set max_attempts = 3
set succeeded = false

while attempt < max_attempts and not succeeded:
    set delay = time.backoff_delay(attempt, 1)
    print "attempt " + str(attempt) + ", would wait " + str(delay) + "s on failure"

    try:
        run tls "example.com" as result
        set succeeded = true
    except err:
        print "  failed: " + str(err)
        sleep delay
    end

    set attempt = attempt + 1
end

print "succeeded: " + str(succeeded)
```

## Extract indicators from unstructured text

```
import "lib/regex.nyx" as re

set log_line = "Server logs: connection from 10.0.0.5, alert sent to admin@example.com, see https://example.com/incident/42 for details"

print re.extract_ips(log_line)      # [10.0.0.5]
print re.extract_emails(log_line)   # [admin@example.com]
print re.extract_urls(log_line)     # [https://example.com/incident/42]
```

Useful for pulling structured indicators out of a `raw_data` blob a
module returned, or any free-text field before deciding what to do with
it.

## Group findings by severity across several targets

```
import "lib/lambdas.nyx" as fn

set targets = ["example.com", "openai.com"]
set all_findings = []

foreach target in targets:
    run audit target as results
    foreach r in results:
        set all_findings = all_findings + r.findings
    end
end

set grouped = fn.group_by(all_findings, lambda(f): f.severity)
foreach severity in keys(grouped):
    print severity + ": " + str(len(grouped[severity]))
end
```

## An interactive triage script

```
if ui.confirm("Audit example.com now?"):
    run audit "example.com" as results
    set all_findings = []
    foreach r in results:
        set all_findings = all_findings + r.findings
    end

    set worrying = filter(all_findings, lambda(f): f.severity == "high" or f.severity == "critical")
    if len(worrying) > 0:
        ui.table(["severity", "title"], map(worrying, lambda(f): [f.severity, f.title]))
        if ui.confirm(str(len(worrying)) + " high+ finding(s) — save a report?"):
            set path = ui.input("Report path: ")
            save results to path
        end
    else:
        ui.status("Nothing high-severity — clean.")
    end
end
```

Works identically under `nyx script run script.nyx` and inside `nyx
tui`'s Script tab — see
[Language Guide § Interactive prompts](NyxScript-Language-Guide#interactive-prompts--ui).

## Filter targets before auditing them (avoid wasting round-trips)

```
import "lib/validate.nyx" as validate
import "lib/net.nyx" as net

set candidates = ["example.com", "10.0.0.5", "not a domain", "openai.com"]

set public_domains = filter(candidates, lambda(c): validate.is_valid_domain(c) and not net.is_private_ipv4(c))

print public_domains
foreach target in public_domains:
    run audit target as results
    print target + " audited"
end
```

## See also

- [NyxScript Language Guide](NyxScript-Language-Guide) — the language
  itself.
- [NyxScript Standard Library Reference](NyxScript-Standard-Library-Reference)
  — every function used above, and everything else available.
- [Glossary](Glossary) — what `ModuleResult`/`Finding`/`Severity`/etc.
  actually are.
