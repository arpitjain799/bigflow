import os
import shutil
import datetime
import subprocess

from datetime import timedelta

from pathlib import Path
from unittest import TestCase, mock

import bigflow.build.spec as spec

from bigflow.cli import walk_module_files
from bigflow.build.dist import SETUP_VALIDATION_MESSAGE

from bigflow.commons import (
    get_docker_image_id,
    build_docker_image_tag,
)
from bigflow.build import (
    auto_configuration,
    project_setup,
)
from bigflow.build.operate import (
    clear_image_leftovers,
    clear_dags_leftovers,
    clear_package_leftovers,
    build_image,
)


PROJECT_NAME = 'main_package'
DOCKER_REPOSITORY = 'test_docker_repository'

TEST_PROJECT_PATH = Path(__file__).parent.parent / 'example_project'
IMAGE_DIR_PATH = TEST_PROJECT_PATH / '.image'
DAGS_DIR_PATH = TEST_PROJECT_PATH / '.dags'
DIST_DIR_PATH = TEST_PROJECT_PATH / 'dist'
EGGS_DIR_PATH = TEST_PROJECT_PATH / f'{PROJECT_NAME}.egg-info'
BUILD_PATH = TEST_PROJECT_PATH / 'build'


class TestProject:
    def run_build(self, cmd: str):
        output = subprocess.getoutput(f'cd {TEST_PROJECT_PATH};{cmd}')
        print(output)
        return output


def mkdir(dir_path: Path):
    if not os.path.isdir(dir_path):
        os.mkdir(dir_path)


def rmdir(dir_path: Path):
    if dir_path.exists() and dir_path.is_dir():
        shutil.rmtree(dir_path)


def create_image_leftovers(test_project_dir_path: Path = TEST_PROJECT_PATH):
    mkdir(test_project_dir_path / '.image')
    (test_project_dir_path / '.image' / 'leftover').touch()


def create_package_leftovers(
        test_project_dir_path: Path = TEST_PROJECT_PATH,
        project_name: str = PROJECT_NAME):
    mkdir(test_project_dir_path / 'build')
    (test_project_dir_path / 'build' / 'leftover').touch()
    mkdir(test_project_dir_path / 'dist')
    (test_project_dir_path / 'dist' / 'leftover').touch()
    mkdir(test_project_dir_path / f'{project_name}.egg-info')
    (test_project_dir_path / f'{project_name}.egg-info' / 'leftover').touch()


def create_dags_leftovers(test_project_dir_path: Path = TEST_PROJECT_PATH):
    mkdir(test_project_dir_path / '.dags')
    (test_project_dir_path / '.dags' / 'leftover').touch()


def dags_leftovers_exist(test_project_dir_path: Path = TEST_PROJECT_PATH):
    return os.path.exists(test_project_dir_path / '.dags' / 'leftover')


def package_leftovers_exist(
        test_project_dir_path: Path = TEST_PROJECT_PATH,
        project_name: str = PROJECT_NAME):
    return os.path.exists(test_project_dir_path / 'build' / 'leftover') and\
           os.path.exists(test_project_dir_path / 'dist' / 'leftover') and\
           os.path.exists(test_project_dir_path / f'{project_name}.egg-info' / 'leftover')


def image_leftovers_exist(test_project_dir_path: Path = TEST_PROJECT_PATH):
    return os.path.exists(test_project_dir_path / '.image' / 'leftover')


def dir_not_empty(dir_path: Path):
    return len(os.listdir(dir_path)) != 0


def deployment_config_copied(test_project_dir_path: Path = TEST_PROJECT_PATH):
    return (test_project_dir_path / '.image' / 'deployment_config.py').exists()


def python_package_built(test_project_dir_path: Path = TEST_PROJECT_PATH):
    return (test_project_dir_path / 'dist' / 'main_package-0.1.0-py3-none-any.whl').exists()


def test_run(test_project_dir_path: Path = TEST_PROJECT_PATH):
    return (test_project_dir_path / 'build' / 'junit-reports').exists()


def dags_built(test_project_dir_path: Path, expected_workflow_count: int):
    if not (test_project_dir_path / '.dags').exists():
        return False
    wff = [
        workflow_name for workflow_dir, workflow_name in
        walk_module_files(test_project_dir_path / '.dags')
    ]
    workflows_count = sum(
        1 for workflow_dir, workflow_name in
        walk_module_files(test_project_dir_path / '.dags')
        if 'workflow' in workflow_name
    )
    return workflows_count == expected_workflow_count


def docker_image_as_file_built(test_project_dir_path: Path = TEST_PROJECT_PATH):
    return (test_project_dir_path / '.image' / 'image-0.1.0.tar').exists()


def docker_image_built_in_registry(docker_repository: str, version: str):
    return get_docker_image_id(build_docker_image_tag(docker_repository, version))


def dags_contain(test_project_dir_path: Path, substring: str):
    for module_dir, module_file_name in walk_module_files(test_project_dir_path / '.dags'):
        with open(os.path.join(module_dir, module_file_name), 'r') as f:
            content = f.read()
            if substring not in content:
                return False
    return True


class SetupTestCase(TestCase):
    def setUp(self) -> None:
        self.test_project = TestProject()
        self.prj = spec.parse_project_spec(
            name=PROJECT_NAME,
            project_dir=TEST_PROJECT_PATH,
            docker_repository=DOCKER_REPOSITORY,
            requries=[],
        )


class BuildProjectE2E(SetupTestCase):

    def test_should_build_project_artifacts(self):
        # when
        create_package_leftovers()
        create_image_leftovers()
        create_dags_leftovers()
        self.test_project.run_build('python setup.py build_project')

        # then
        self.assertTrue(python_package_built())
        self.assertTrue(test_run())
        self.assertTrue(dags_built(TEST_PROJECT_PATH, 2))

        self.assertTrue(docker_image_as_file_built())
        self.assertFalse(docker_image_built_in_registry(DOCKER_REPOSITORY, '0.1.0'))
        self.assertTrue(deployment_config_copied())
        self.assertTrue((TEST_PROJECT_PATH / "resources" / "requirements.txt").exists())

        # and
        self.assertFalse(package_leftovers_exist())
        self.assertFalse(image_leftovers_exist())
        self.assertFalse(dags_leftovers_exist())

    def test_should_validate_project_setup(self):
        # expected
        self.assertTrue(SETUP_VALIDATION_MESSAGE in self.test_project.run_build('python setup.py build_project --validate-project-setup'))
        self.assertTrue(SETUP_VALIDATION_MESSAGE in self.test_project.run_build('python setup.py build_project --build-dags --validate-project-setup'))
        self.assertTrue(SETUP_VALIDATION_MESSAGE in self.test_project.run_build('python setup.py build_project --build-image --validate-project-setup'))
        self.assertTrue(SETUP_VALIDATION_MESSAGE in self.test_project.run_build('python setup.py build_project --build-package --validate-project-setup'))


class BuildPackageCommandE2E(SetupTestCase):
    def test_should_execute_build_package_command(self):
        # given
        create_package_leftovers(self.prj.project_dir)
        clear_image_leftovers(self.prj)
        clear_dags_leftovers(self.prj)

        # when
        self.test_project.run_build('python setup.py build_project --build-package')

        # then
        self.assertTrue(python_package_built())
        self.assertTrue(test_run())
        self.assertFalse(package_leftovers_exist())


class BuildDagsCommandE2E(SetupTestCase):

    def test_should_execute_build_dags_command(self):

        # given
        create_dags_leftovers(self.prj.project_dir)
        clear_image_leftovers(self.prj)
        clear_package_leftovers(self.prj)

        # when
        self.test_project.run_build('python setup.py build_project --build-dags')

        # then
       # self.assertTrue(dags_built(TEST_PROJECT_PATH, 2))
        self.assertFalse(dags_leftovers_exist(TEST_PROJECT_PATH))
        self.assertTrue(dags_contain(TEST_PROJECT_PATH, repr(datetime.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(hours=24))))

        # when
        self.test_project.run_build("python setup.py build_project --build-dags --start-time '2020-01-02 00:00:00'")

        # then
        self.assertTrue(dags_contain(TEST_PROJECT_PATH, 'datetime.datetime(2020, 1, 1, 0, 0)'))

        # when
        self.test_project.run_build('python setup.py build_project --build-dags --workflow workflow1')

        # then
        self.assertTrue(self.single_dag_for_workflow_exists('workflow1'))

    def single_dag_for_workflow_exists(self, workflow_id):
        dags_created = dir_not_empty(TEST_PROJECT_PATH / '.dags')
        if not dags_created:
            return False
        dag_file_path = os.path.join(*next(walk_module_files(TEST_PROJECT_PATH / '.dags')))
        with open(dag_file_path, 'r') as f:
            return workflow_id in f.read()


class BuildImageCommandE2E(SetupTestCase):

    def test_should_execute_build_image_command(self):

        # given
        create_image_leftovers(self.prj.project_dir)
        clear_dags_leftovers(self.prj)
        clear_package_leftovers(self.prj)

        self.test_project.run_build('python setup.py build_project --build-package')

        # when
        self.test_project.run_build('python setup.py build_project --build-image')

        # then
        self.assertFalse(image_leftovers_exist())
        self.assertFalse(docker_image_built_in_registry(DOCKER_REPOSITORY, '0.1.0'))
        self.assertTrue(docker_image_as_file_built())
        self.assertTrue(deployment_config_copied())


class BuildImageTest(SetupTestCase):

    @mock.patch('bigflow.commons.build_docker_image_tag')
    @mock.patch('bigflow.build.operate._build_docker_image')
    @mock.patch('bigflow.build.operate._export_docker_image_to_file')
    @mock.patch('bigflow.commons.remove_docker_image_from_local_registry')
    def test_should_remove_image_from_local_registry_when_export_to_image_failed(self,
                                                                                 remove_docker_image_from_local_registry,
                                                                                 export_docker_image_to_file,
                                                                                 build_docker_image: mock.Mock,
                                                                                 build_docker_image_tag):
        # given
        image_dir_path = Path('image_dir')
        rmdir(image_dir_path)
        export_docker_image_to_file.side_effect = Exception('export failed')
        build_docker_image_tag.return_value = 'tag_value'

        # when:
        with self.assertRaises(Exception):
            build_image(self.prj)

        # then
        build_docker_image.assert_called_with(self.prj.project_dir, 'tag_value')
        remove_docker_image_from_local_registry.assert_called_with('tag_value')
