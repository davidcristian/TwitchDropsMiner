from __future__ import annotations

import io
import sys

from sources import write_utf8


def test_write_utf8_makes_an_output_in_a_code_page_write_utf8(monkeypatch):
    written = io.BytesIO()
    monkeypatch.setattr(sys, "stdout", io.TextIOWrapper(written, encoding="cp1252", newline="\n"))
    write_utf8()
    print("Română")
    sys.stdout.flush()
    assert written.getvalue() == "Română\n".encode("utf-8")


def test_write_utf8_leaves_an_output_that_has_no_encoding(monkeypatch):
    output = io.StringIO()
    monkeypatch.setattr(sys, "stdout", output)
    write_utf8()
    print("Română")
    assert (sys.stdout, output.getvalue()) == (output, "Română\n")
