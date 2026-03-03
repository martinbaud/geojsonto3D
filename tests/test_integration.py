"""
Integration tests for GeoJSON to 3D Globe application
"""

import unittest
import sys
import json
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))


class TestProjectStructure(unittest.TestCase):
    """Test project structure and files"""

    def setUp(self):
        """Set up test environment"""
        self.project_root = Path(__file__).parent.parent

    def test_src_directory_exists(self):
        """Test that src directory exists"""
        self.assertTrue((self.project_root / 'src').exists())

    def test_data_directory_exists(self):
        """Test that data directory exists"""
        self.assertTrue((self.project_root / 'data').exists())

    def test_res_directory_exists(self):
        """Test that res directory exists"""
        self.assertTrue((self.project_root / 'res').exists())

    def test_main_launcher_exists(self):
        """Test that main launcher exists"""
        self.assertTrue((self.project_root / 'main.py').exists())

    def test_blender_runner_exists(self):
        """Test that blender_runner module exists"""
        self.assertTrue((self.project_root / 'src' / 'blender_runner.py').exists())

    def test_blender_script_exists(self):
        """Test that Blender script exists"""
        self.assertTrue((self.project_root / 'src' / 'run.py').exists())

    def test_readme_exists(self):
        """Test that README exists"""
        self.assertTrue((self.project_root / 'README.md').exists())

    def test_gitignore_exists(self):
        """Test that .gitignore exists"""
        self.assertTrue((self.project_root / '.gitignore').exists())


class TestCacheIntegration(unittest.TestCase):
    """Test cache file operations in realistic scenarios"""

    def setUp(self):
        """Set up test environment with temp directory"""
        self.test_dir = tempfile.mkdtemp()
        self.cache_file = Path(self.test_dir) / '.test_cache.json'

    def tearDown(self):
        """Clean up test directory"""
        shutil.rmtree(self.test_dir)

    def test_cache_roundtrip(self):
        """Test saving and loading cache"""
        from blender_runner import save_cache, load_cache

        test_data = {
            'blender_path': '/usr/bin/blender',
            'version': '4.4'
        }

        # Save cache
        result = save_cache(str(self.cache_file), test_data)
        self.assertTrue(result)

        # Load cache
        loaded_data = load_cache(str(self.cache_file))
        self.assertEqual(loaded_data, test_data)

    def test_multiple_cache_operations(self):
        """Test multiple save/load operations"""
        from blender_runner import save_cache, load_cache

        # First save
        data1 = {'blender_path': '/path/1'}
        save_cache(str(self.cache_file), data1)
        self.assertEqual(load_cache(str(self.cache_file)), data1)

        # Update cache
        data2 = {'blender_path': '/path/2', 'extra': 'value'}
        save_cache(str(self.cache_file), data2)
        self.assertEqual(load_cache(str(self.cache_file)), data2)


class TestConfigIntegration(unittest.TestCase):
    """Test configuration flow"""

    def test_preset_to_args_conversion(self):
        """Test full preset to script args conversion"""
        from blender_runner import PRESETS, build_script_args

        for preset_name in ['low', 'medium', 'high', 'ultra']:
            config = PRESETS[preset_name].copy()
            args = build_script_args(config)

            # Verify all critical args are present
            self.assertIn('--ico-subdiv', args)
            self.assertIn('--extrude-above', args)
            self.assertIn('--extrude-below', args)

            # Verify boolean flags
            if config['enable_borders']:
                self.assertIn('--enable-border', args)
            else:
                self.assertIn('--disable-border', args)

            if config['enable_cities']:
                self.assertIn('--enable-cities', args)
            else:
                self.assertIn('--disable-cities', args)


class TestImports(unittest.TestCase):
    """Test that all modules can be imported"""

    def test_import_blender_runner(self):
        """Test importing blender_runner module"""
        try:
            import blender_runner
            self.assertTrue(hasattr(blender_runner, 'main'))
            self.assertTrue(hasattr(blender_runner, 'PRESETS'))
        except ImportError as e:
            self.fail(f"Failed to import blender_runner: {e}")

    def test_launcher_imports(self):
        """Test that launcher can import blender_runner"""
        launcher_path = Path(__file__).parent.parent / 'main.py'

        # Read launcher file with proper encoding
        with open(launcher_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Check for proper imports
        self.assertIn('from blender_runner import main', content)


class TestGitignore(unittest.TestCase):
    """Test .gitignore configuration"""

    def setUp(self):
        """Set up test environment"""
        self.project_root = Path(__file__).parent.parent
        self.gitignore_path = self.project_root / '.gitignore'

    def test_cache_files_ignored(self):
        """Test that cache files are in .gitignore"""
        with open(self.gitignore_path, 'r') as f:
            content = f.read()

        self.assertIn('.blender_cache.json', content)
        self.assertIn('.config_cache.json', content)

    def test_output_files_ignored(self):
        """Test that output files are in .gitignore"""
        with open(self.gitignore_path, 'r') as f:
            content = f.read()

        self.assertIn('res/*.glb', content)

    def test_python_artifacts_ignored(self):
        """Test that Python artifacts are in .gitignore"""
        with open(self.gitignore_path, 'r') as f:
            content = f.read()

        self.assertIn('__pycache__/', content)
        # Check for Python compiled files (*.pyc or *.py[cod])
        self.assertTrue('*.pyc' in content or '*.py[cod]' in content)


class TestREADME(unittest.TestCase):
    """Test README documentation"""

    def setUp(self):
        """Set up test environment"""
        self.project_root = Path(__file__).parent.parent
        self.readme_path = self.project_root / 'README.md'

    def test_readme_has_usage_section(self):
        """Test that README has usage section"""
        with open(self.readme_path, 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertIn('## Usage', content)

    def test_readme_has_presets_documented(self):
        """Test that all presets are documented in README"""
        with open(self.readme_path, 'r', encoding='utf-8') as f:
            content = f.read()

        presets = ['low', 'medium', 'high', 'ultra']
        for preset in presets:
            self.assertIn(preset, content.lower())

    def test_readme_has_installation_section(self):
        """Test that README has installation section"""
        with open(self.readme_path, 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertIn('## Installation', content)


if __name__ == '__main__':
    unittest.main()
