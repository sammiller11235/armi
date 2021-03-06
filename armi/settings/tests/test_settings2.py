# Copyright 2019 TerraPower, LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Tests for new settings system with plugin import"""
import unittest
import io
import copy
import os

from ruamel.yaml import YAML
import voluptuous as vol

import armi
from armi.physics.fuelCycle import FuelHandlerPlugin
from armi import settings
from armi.settings import caseSettings
from armi.settings import setting2 as setting
from armi.operators import settingsValidation
from armi import plugins

THIS_DIR = os.path.dirname(__file__)
TEST_XML = os.path.join(THIS_DIR, "old_xml_settings_input.xml")


class DummyPlugin1(plugins.ArmiPlugin):
    @staticmethod
    @plugins.HOOKIMPL
    def defineSettings():
        return [
            setting.Setting(
                "extendableOption",
                default="DEFAULT",
                label="Neutronics Kernel",
                description="The neutronics / depletion solver for global flux solve.",
                enforcedOptions=True,
                options=["DEFAULT", "OTHER"],
            )
        ]


class DummyPlugin2(plugins.ArmiPlugin):
    @staticmethod
    @plugins.HOOKIMPL
    def defineSettings():
        return [setting.Option("PLUGIN", "extendableOption")]


class TestSettings2(unittest.TestCase):
    def setUp(self):
        # We are going to be messing with the plugin manager, which is global ARMI
        # state, so we back it up and restore the original when we are done.
        self._backupApp = copy.copy(armi._app)

    def tearDown(self):
        armi._app = self._backupApp

    def testSchemaChecksType(self):
        newSettings = FuelHandlerPlugin.defineSettings()

        GOOD_INPUT = io.StringIO(
            """
assemblyRotationAlgorithm: buReducingAssemblyRotation
shuffleLogic: {}
""".format(
                __file__
            )
        )

        BAD_INPUT = io.StringIO(
            """
assemblyRotationAlgorithm: buReducingAssemblyRotatoin
"""
        )

        yaml = YAML()

        inp = yaml.load(GOOD_INPUT)
        for inputSetting, inputVal in inp.items():
            setting = [
                setting for setting in newSettings if setting.name == inputSetting
            ][0]
            setting.schema(inputVal)

        inp = yaml.load(BAD_INPUT)
        for inputSetting, inputVal in inp.items():
            with self.assertRaises(vol.error.MultipleInvalid):
                setting = [
                    setting for setting in newSettings if setting.name == inputSetting
                ][0]
                setting.schema(inputVal)

    def test_listsMutable(self):
        listSetting = setting.Setting(
            "aList", default=[], label="Dummy list", description="whatever"
        )

        listSetting.value = [1, 2, 3]
        self.assertEqual([1, 2, 3], listSetting.value)

        listSetting.value[-1] = 4
        self.assertEqual([1, 2, 4], listSetting.value)

    def test_listCoercion(self):
        """Make sure list setting values get coerced right."""
        listSetting = setting.Setting(
            "aList", default=[0.2, 5], label="Dummy list", description="whatever"
        )
        listSetting.value = [1, 2, 3]
        self.assertEqual(listSetting.value, [1.0, 2.0, 3.0])
        self.assertTrue(isinstance(listSetting.value[0], float))

    def test_typeDetection(self):
        """Ensure some of the type inference operations work."""
        listSetting = setting.Setting(
            "aList",
            default=[],
            label="label",
            description="desc",
            schema=vol.Schema([float]),
        )
        self.assertEqual(listSetting.containedType, float)
        listSetting = setting.Setting(
            "aList",
            default=[],
            label="label",
            description="desc",
            schema=vol.Schema([vol.Coerce(float)]),
        )
        self.assertEqual(listSetting.containedType, float)

    def test_csWorks(self):
        """Ensure plugin settings become available and have defaults"""
        a = settings.getMasterCs()
        self.assertEqual(a["circularRingOrder"], "angle")

    def test_pluginValidatorsAreDiscovered(self):
        cs = caseSettings.Settings()
        cs["shuffleLogic"] = "nothere"
        inspector = settingsValidation.Inspector(cs)
        self.assertTrue(
            any(
                [
                    "Shuffling will not occur" in query.statement
                    for query in inspector.queries
                ]
            )
        )

    def test_options(self):
        pm = armi.getPluginManagerOrFail()
        pm.register(DummyPlugin1)
        # We have a setting; this should be fine
        cs = caseSettings.Settings()
        self.assertEqual(cs["extendableOption"], "DEFAULT")
        # We shouldn't have any settings from the other plugin, so this should be an
        # error.
        with self.assertRaises(vol.error.MultipleInvalid):
            cs["extendableOption"] = "PLUGIN"

        pm.register(DummyPlugin2)
        cs = caseSettings.Settings()
        self.assertEqual(cs["extendableOption"], "DEFAULT")
        # Now we should have the option from plugin 2; make sure that works
        cs["extendableOption"] = "PLUGIN"
        pm.unregister(DummyPlugin2)
        pm.unregister(DummyPlugin1)

        # Now try the same, but adding the plugins in a different order. This is to make
        # sure that it doesnt matter if the Setting or its Options come first
        pm.register(DummyPlugin2)
        pm.register(DummyPlugin1)
        cs = caseSettings.Settings()
        self.assertEqual(cs["extendableOption"], "DEFAULT")
        cs["extendableOption"] = "PLUGIN"

    def test_default(self):
        """Make sure default updating mechanism works."""
        a = setting.Setting("testsetting", 0)
        newDefault = setting.Default(5, "testsetting")
        a.changeDefault(newDefault)
        self.assertEqual(a.value, 5)


class TestSettingsConversion(unittest.TestCase):
    """Make sure we can convert from old XML type settings to new Yaml settings."""

    def test_convert(self):
        cs = caseSettings.Settings()
        cs.loadFromInputFile(TEST_XML)
        self.assertEqual(cs["buGroups"], [3, 10, 20, 100])

    def test_empty(self):
        cs = caseSettings.Settings()
        cs["buGroups"] = []
        self.assertEqual(cs["buGroups"], [])


if __name__ == "__main__":
    # import sys;sys.argv = ['', 'Test.testName']
    unittest.main()
