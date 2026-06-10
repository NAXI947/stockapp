from __future__ import annotations

import unittest

from backend.app.data_health import TABLE_SPECS


class DataHealthUpdateNotesTest(unittest.TestCase):
    def test_update_notes_describe_four_full_update_entries(self) -> None:
        notes = "\n".join(str(spec.get("updater", "")) for spec in TABLE_SPECS)

        self.assertIn("全量日更", notes)
        self.assertIn("全量周更", notes)
        self.assertIn("全量月更", notes)
        self.assertIn("全量年更", notes)
        self.assertNotIn("更新历史数据", notes)
        self.assertNotIn("更新季频数据", notes)
        self.assertNotIn("--light", notes)
        self.assertNotIn("--latest-only", notes)

    def test_financial_indicator_is_documented_under_yearly_update(self) -> None:
        fin_spec = next(spec for spec in TABLE_SPECS if spec["table"] == "t_fin_indicator")

        self.assertIn("全量年更", fin_spec["updater"])


if __name__ == "__main__":
    unittest.main()
