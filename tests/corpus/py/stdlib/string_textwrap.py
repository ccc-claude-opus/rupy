import string
import textwrap
from string import Template

print(string.ascii_letters, string.digits, string.hexdigits, string.octdigits, repr(string.whitespace))
print(string.punctuation, len(string.printable), repr(string.printable[-6:]))
print(string.capwords("  hello   wORLD  of python "), string.capwords("a-b-c", "-"), string.capwords(""))
t = Template("$who likes ${what}; $$5 and $who again")
print(t.substitute({"who": "tim", "what": "kung pao"}), t.safe_substitute({"who": "ann"}), t.get_identifiers())
for k in range(3):
    try:
        if k == 0:
            Template("$who $x").substitute({"who": "a"})
        elif k == 1:
            Template("line\nab $ 1").substitute({})
        else:
            Template("${bad").substitute({})
    except KeyError as e:
        print("KeyError", e)
    except ValueError as e:
        print("ValueError", e)

TEXT = "The quick brown fox jumps over the lazy dog. Look, goof-ball -- use the -b option! A well-known, state-of-the-art e-mail address: x--y and pre---post. Supercalifragilisticexpialidocious words break."
for w in [10, 15, 20, 33, 70]:
    print(w, textwrap.wrap(TEXT, w))
print(textwrap.wrap(TEXT, 12, break_on_hyphens=False))
print(textwrap.wrap(TEXT, 12, break_long_words=False))
print(textwrap.fill(TEXT, 30, initial_indent="* ", subsequent_indent="  "))
print(textwrap.wrap(TEXT, 25, max_lines=3), textwrap.wrap(TEXT, 25, max_lines=2, placeholder=" ..."))
print(textwrap.wrap("tab\tseparated\ttext\there", 12), textwrap.wrap("tab\tsep", 20, expand_tabs=False))
print(textwrap.wrap("Hello there.  How are you? I am fine.\nNew line.", 40, fix_sentence_endings=True))
print(textwrap.wrap("  leading and trailing  ", 10), textwrap.wrap("  leading and trailing  ", 10, drop_whitespace=False))
print(repr(textwrap.shorten("Hello  world!", width=12)), repr(textwrap.shorten("Hello  world!", width=11)), repr(textwrap.shorten(TEXT, 40, placeholder="...")))
print(repr(textwrap.dedent("    def f():\n        return 1\n\n    x = 2\n")), repr(textwrap.dedent("\thello\n  there")), repr(textwrap.dedent("  a\n   \n  b")))
print(repr(textwrap.indent("one\n\ntwo\n  \nthree", "> ")), repr(textwrap.indent("a\nb\n", "+", lambda line: line.startswith("b"))))
try:
    textwrap.wrap(TEXT, 0)
except ValueError as e:
    print("ValueError", e)
