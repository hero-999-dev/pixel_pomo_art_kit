import unittest

from art_kit import i18n


class I18nTest(unittest.TestCase):
    def tearDown(self):
        i18n.set_language("en")

    def test_missing_keys_fall_back_to_english(self):
        i18n.set_language("tr")
        self.assertEqual(i18n.t("save"), "KAYDET")
        self.assertEqual(i18n.t("pixels", n=4), "piksel 4")
        i18n.set_language("de")
        self.assertEqual(i18n.t("help"), "HILFE")
        i18n.set_language("pl")
        self.assertEqual(i18n.t("all"), "WSZYSTKO")

    def test_unknown_language_is_english(self):
        self.assertEqual(i18n.set_language("xx"), "en")
        self.assertEqual(i18n.t("save"), "SAVE")
