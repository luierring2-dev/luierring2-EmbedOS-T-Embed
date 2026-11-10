import codecs
import os
import tempfile
import unittest
from pathlib import Path

from logtail import LogTail, Matcher, template


class LogTailTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.path = self.dir / "FortniteGame.log"

    def append(self, data: bytes):
        with open(self.path, "ab") as f:
            f.write(data)

    def test_skips_old_history_on_start(self):
        self.append(b"gammel linje\n")
        tail = LogTail(self.path)
        self.assertEqual(tail.poll(), [])
        self.append(b"ny linje\n")
        self.assertEqual(tail.poll(), ["ny linje"])

    def test_partial_line_is_held_back(self):
        self.append(b"")
        tail = LogTail(self.path)
        tail.poll()
        self.append(b"Match State Changed from Waiting")
        self.assertEqual(tail.poll(), [])
        self.append(b"ToStart to InProgress\r\nnext")
        self.assertEqual(tail.poll(), ["Match State Changed from WaitingToStart to InProgress"])

    def test_missing_file_then_created_reads_from_start(self):
        tail = LogTail(self.path)
        self.assertEqual(tail.poll(), [])
        self.assertFalse(tail.exists)
        self.append(b"first\nsecond\n")
        self.assertEqual(tail.poll(), ["first", "second"])

    def test_rotation_new_file_read_from_start(self):
        self.append(b"old\n" * 100)
        tail = LogTail(self.path)
        tail.poll()
        # Fortnite starter: gammel log omdøbes, ny oprettes (større end ingenting, mindre end før)
        os.rename(self.path, self.dir / "FortniteGame-backup-2026.11.10.log")
        self.append(b"fresh 1\nfresh 2\n")
        self.assertEqual(tail.poll(), ["fresh 1", "fresh 2"])
        self.assertEqual(tail.rotations, 1)

    def test_rotation_detected_even_if_new_file_is_bigger(self):
        self.append(b"x\n")
        tail = LogTail(self.path)
        tail.poll()
        os.rename(self.path, self.dir / "backup.log")
        self.append(b"line\n" * 50)
        self.assertEqual(len(tail.poll()), 50)       # den gamle version ville springe dem over

    def test_truncation(self):
        self.append(b"a\nb\nc\n")
        tail = LogTail(self.path)
        tail.poll()
        with open(self.path, "wb") as f:
            f.write(b"z\n")
        self.assertEqual(tail.poll(), ["z"])

    def test_utf8_multibyte_split_across_reads(self):
        self.append(b"")
        tail = LogTail(self.path)
        tail.poll()
        data = "kiste åbnet ø\n".encode("utf-8")
        cut = data.index("ø".encode()) + 1
        self.append(data[:cut])
        self.assertEqual(tail.poll(), [])
        self.append(data[cut:])
        self.assertEqual(tail.poll(), ["kiste åbnet ø"])

    def test_utf8_bom(self):
        tail = LogTail(self.path)
        tail.poll()
        self.append(codecs.BOM_UTF8 + b"hello\n")
        self.assertEqual(tail.poll(), ["hello"])

    def test_utf16_with_bom(self):
        tail = LogTail(self.path)
        tail.poll()
        self.append("Match State Changed from A to InProgress\r\nnæste\r\n".encode("utf-16"))
        self.assertEqual(tail.poll(), ["Match State Changed from A to InProgress", "næste"])

    def test_utf16_tail_from_middle(self):
        self.append("gammel\r\n".encode("utf-16"))
        tail = LogTail(self.path)
        tail.poll()
        self.append("ny\r\n".encode("utf-16-le"))
        self.assertEqual(tail.poll(), ["ny"])

    def test_large_file_read_in_chunks(self):
        tail = LogTail(self.path)
        tail.poll()
        line = b"y" * 99 + b"\n"
        self.append(line * 50000)                      # ~5 MB
        total = 0
        for _ in range(10):
            total += len(tail.poll())
        self.assertEqual(total, 50000)


class MatcherTest(unittest.TestCase):
    def test_lists_strings_notes_and_errors(self):
        m = Matcher({"_note": "ignoreres", "MATCH_START": ["to InProgress"], "LOBBY": "Frontend",
                     "CHEST": [], "BAD": ["(unclosed"]})
        self.assertEqual(m.match("Match State Changed from X to InProgress"), "MATCH_START")
        self.assertEqual(m.match("LoadMap /Game/Maps/Frontend"), "LOBBY")
        self.assertIsNone(m.match("nothing"))
        self.assertEqual(m.events(), {"MATCH_START", "LOBBY"})
        self.assertEqual(len(m.errors), 1)

    def test_case_insensitive(self):
        self.assertEqual(Matcher({"E": ["chest"]}).match("CHEST opened"), "E")


class TemplateTest(unittest.TestCase):
    def test_strips_timestamp_and_numbers(self):
        a = template("[2026.11.10-15.14.33:123][ 45]LogX: Tiered_Chest_C_12 opened at 1.5")
        b = template("[2026.11.10-16.00.01:999][812]LogX: Tiered_Chest_C_7 opened at 22.25")
        self.assertEqual(a, b)
        self.assertEqual(a, "LogX: Tiered_Chest_C_# opened at #")

    def test_hex(self):
        self.assertEqual(template("ptr 0x7ff6a1b2c3d4 id DEADBEEF01"), "ptr # id #")


if __name__ == "__main__":
    unittest.main()
