"""validate.py のテスト。Qt を使わない。"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import validate  # noqa: E402


def rows(*entries):
    """(名前, 幅, wire) のリストにする。wire を省くと None (Wire 列なし)。"""
    return [tuple(entry) + (None,) * (3 - len(entry)) for entry in entries]


class IdentifierTest(unittest.TestCase):
    def test_valid(self):
        for name in ("a", "_x", "data_in", "q0", "n$1"):
            self.assertEqual(validate.identifier_problem(name), "", name)

    def test_keyword(self):
        problem = validate.identifier_problem("wire")
        self.assertIn("予約語", problem)

    def test_bad_characters(self):
        for name in ("1a", "a-b", "a b", "ポート", ""):
            self.assertNotEqual(validate.identifier_problem(name), "", name)


class WidthTest(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(validate.width_problem("1"), "")
        self.assertEqual(validate.width_problem("32"), "")

    def test_empty(self):
        self.assertIn("空", validate.width_problem(""))

    def test_not_a_number(self):
        self.assertIn("数値", validate.width_problem("8bit"))

    def test_zero_or_negative(self):
        self.assertIn("1 以上", validate.width_problem("0"))
        self.assertIn("1 以上", validate.width_problem("-3"))


class CheckTest(unittest.TestCase):
    def test_clean_module(self):
        errors, warnings = validate.check("top", rows(("a", "1")), rows(("y", "8")))
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])

    def test_empty_module_name(self):
        errors, _ = validate.check("  ", rows(("a", "1")), [])
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0].where, "module_name")

    def test_empty_port_name_points_at_the_cell(self):
        errors, _ = validate.check("top", rows(("", "1")), [])
        self.assertEqual(len(errors), 1)
        issue = errors[0]
        self.assertEqual((issue.where, issue.row, issue.column),
                         ("inputs", 0, validate.COL_NAME))

    def test_bad_width_points_at_the_cell(self):
        errors, _ = validate.check("top", rows(("a", "8bit")), [])
        self.assertEqual(len(errors), 1)
        issue = errors[0]
        self.assertEqual((issue.where, issue.row, issue.column),
                         ("inputs", 0, validate.COL_WIDTH))

    def test_duplicate_within_inputs(self):
        errors, _ = validate.check("top", rows(("a", "1"), ("a", "1")), [])
        self.assertEqual(len(errors), 1)
        self.assertIn("重複", errors[0].message)
        self.assertEqual(errors[0].row, 1)

    def test_duplicate_across_input_and_output(self):
        errors, _ = validate.check("top", rows(("a", "1")), rows(("a", "1")))
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0].where, "outputs")

    def test_reserved_word_as_port_name(self):
        errors, _ = validate.check("top", rows(("reg", "1")), [])
        self.assertIn("予約語", errors[0].message)

    def test_instance_name_may_be_empty(self):
        errors, _ = validate.check("blk", rows(("a", "1", "net")), [],
                                   instance_name="")
        self.assertEqual(errors, [])

    def test_instance_name_must_be_an_identifier(self):
        errors, _ = validate.check("blk", rows(("a", "1", "net")), [],
                                   instance_name="1st")
        self.assertEqual(errors[0].where, "instance_name")

    def test_missing_wire_name_is_a_warning(self):
        errors, warnings = validate.check("blk", rows(("a", "1", "")), [],
                                          instance_name="u_blk")
        self.assertEqual(errors, [])
        self.assertEqual(len(warnings), 1)
        self.assertEqual((warnings[0].where, warnings[0].column),
                         ("inputs", validate.COL_WIRE))

    def test_no_wire_column_produces_no_warning(self):
        """モジュール側の表は Wire 名の列を持たないので警告しない。"""
        _, warnings = validate.check("top", rows(("a", "1")), rows(("y", "1")))
        self.assertEqual(warnings, [])


if __name__ == "__main__":
    unittest.main()
