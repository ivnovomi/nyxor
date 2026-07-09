"""The starter script written out by ``nyx script new``."""

from __future__ import annotations

TEMPLATE = """\
# NyxScript — batch-drive NYXOR modules. Run `nyx script lint` on this file
# any time; it catches undefined variables and typo'd module names before
# you burn a network round-trip finding out.
#
# Syntax:
#   set NAME = <expr>                literal, variable, or `a + b`/`a == b`/...
#   if EXPR:
#       ...
#   else:
#       ...
#   end
#   foreach VAR in LIST:
#       ...
#   end
#   run <module> <target> [as VAR]   modules: audit, dns, tls, http,
#                                             network.discover, network.scan
#   save VAR to "path.ext"           format from extension: .json/.md/.html
#   print "text with {expressions} and {{literal braces}}"
#   assert EXPR[, "message"]
#   fail "message"
#   sleep SECONDS
#
# Escape hatches (disabled unless run with --unsafe / the TUI's Unsafe toggle):
#   pip "package-name"               installs a package with pip, then...
#   python:                          ...you can import and use it here.
#       ...real Python; reads/writes NyxScript variables directly...
#   end

set targets = ["example.com", "example.org"]
set min_findings = 1

foreach target in targets:
    print "Auditing {target}..."
    run audit target as result

    set count = 0
    foreach r in result:
        set count = count + 1
    end

    if count >= min_findings:
        save result to "nyxor-output/{target}-audit.html"
        print "  saved report for {target}"
    else:
        print "  skipped {target}: nothing came back"
    end
end

print "Done."
"""
