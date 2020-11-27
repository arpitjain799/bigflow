from unittest import TestCase
from unittest.mock import patch

import apache_beam as beam
from apache_beam import Pipeline
from apache_beam.options.pipeline_options import PipelineOptions
from apache_beam.runners.portability.fn_api_runner.fn_runner import RunnerResult
from apache_beam.testing.test_pipeline import TestPipeline
from collections import defaultdict
from bigflow import JobContext, Workflow

from bigflow.dataflow import BeamJob


class CountWordsFn(beam.DoFn):
    def __init__(self, save):
        super().__init__()
        self.save = save

    def process(self, element, *args, **kwargs):
        word, count = element
        self.save.counter[word] += len(count)
        yield word, len(count)


class Save(object):
    counter = defaultdict(int)


class Saver(beam.PTransform):
    def __init__(self, save):
        super().__init__()
        self.save = save

    def expand(self, records_to_delete):
        return records_to_delete \
               | "SaveCountedWords" >> beam.ParDo(
            CountWordsFn(self.save))


class CountWordsDriver:
    def __init__(self, saver):
        self.result = None
        self.context = None
        self.pipeline = None
        self.saver = saver

    def run(self, pipeline: Pipeline, context: JobContext, driver_arguments: dict):
        words_input = pipeline | 'LoadingWordsInput' >> beam.Create(driver_arguments['words_to_count'])
        words_input | 'FilterWords' >> beam.Filter(lambda w: w in driver_arguments['words_to_filter']) \
        | 'MapToCount' >> beam.Map(lambda w: (w, 1))\
        | 'GroupWords' >> beam.GroupByKey()\
        | 'CountWords' >> self.saver
        self.context = context
        self.pipeline = pipeline


class BeamJobTestCase(TestCase):

    @patch.object(RunnerResult, 'is_in_terminal_state', create=True)
    def test_should_run_beam_job(self, is_in_terminal_state_mock):
        # given
        is_in_terminal_state_mock.return_value = True
        options = PipelineOptions()
        driver = CountWordsDriver(Saver(Save()))
        job = BeamJob(
            id='count_words',
            entry_point=driver.run,
            entry_point_arguments={
                'words_to_filter': ['valid', 'word'],
                'words_to_count': ['trash', 'valid', 'word', 'valid']
            },
            pipeline_options=options,
            pipeline=TestPipeline)

        count_words = Workflow(
            workflow_id='count_words',
            definition=[job])

        # when
        count_words.run('2020-01-01')

        # then executes the job with the arguments
        self.assertEqual(driver.saver.save.counter, {'valid': 2, 'word': 1})

        # and passes the context
        self.assertIsNotNone(driver.context)
        self.assertTrue(isinstance(driver.context, JobContext))

        # and labels the job
        self.assertEqual(
            driver.pipeline._options.get_all_options()['labels'],
            ['workflow_id=count_words'])

    @patch.object(RunnerResult, 'is_in_terminal_state', create=True)
    @patch.object(RunnerResult, 'cancel')
    @patch.object(RunnerResult, 'wait_until_finish')
    def test_should_run_beam_job_with_timeout_with_cancel(self, wait_until_finish_mock, cancel_mock, is_in_terminal_state_mock):
        # given
        wait_until_finish_mock.return_value = 'DONE'
        is_in_terminal_state_mock.return_value = False
        options = PipelineOptions()
        driver = CountWordsDriver(Saver(Save()))
        job = BeamJob(
            id='count_words',
            entry_point=driver.run,
            entry_point_arguments={
                'words_to_filter': ['valid', 'word'],
                'words_to_count': ['trash', 'valid', 'word', 'valid']
            },
            pipeline_options=options,
            pipeline=TestPipeline,
            execution_timeout=3)

        count_words = Workflow(
            workflow_id='count_words',
            definition=[job])

        # when
        count_words.run('2020-01-01')

        # then
        self.assertEqual(cancel_mock.call_count, 1)
        wait_until_finish_mock.assert_called_with(3)

    @patch.object(RunnerResult, 'is_in_terminal_state', create=True)
    @patch.object(RunnerResult, 'cancel')
    @patch.object(RunnerResult, 'wait_until_finish')
    def test_should_run_beam_job_with_timeout_without_cancel(self, wait_until_finish_mock, cancel_mock, is_in_terminal_state_mock):
        # given
        wait_until_finish_mock.return_value = 'DONE'
        is_in_terminal_state_mock.return_value = True
        options = PipelineOptions()
        driver = CountWordsDriver(Saver(Save()))
        job = BeamJob(
            id='count_words',
            entry_point=driver.run,
            entry_point_arguments={
                'words_to_filter': ['valid', 'word'],
                'words_to_count': ['trash', 'valid', 'word', 'valid']
            },
            pipeline_options=options,
            pipeline=TestPipeline)

        count_words = Workflow(
            workflow_id='count_words',
            definition=[job])

        # when
        count_words.run('2020-01-01')

        # then
        self.assertEqual(cancel_mock.call_count, 0)
        wait_until_finish_mock.assert_called_with(3600000)

    @patch.object(RunnerResult, 'is_in_terminal_state', create=True)
    @patch.object(RunnerResult, 'cancel')
    def test_should_run_beam_job_without_timeout_if_wait_until_finish_disabled(self, cancel_mock, is_in_terminal_state_mock):
        is_in_terminal_state_mock.return_value = False
        # given
        options = PipelineOptions()
        driver = CountWordsDriver(Saver(Save()))
        job = BeamJob(
            id='count_words',
            entry_point=driver.run,
            entry_point_arguments={
                'words_to_filter': ['valid', 'word'],
                'words_to_count': ['trash', 'valid', 'word', 'valid']
            },
            pipeline_options=options,
            pipeline=TestPipeline,
            execution_timeout=1)

        count_words = Workflow(
            workflow_id='count_words',
            definition=[job])

        # when
        count_words.run('2020-01-01')

        # then executes the job with the arguments
        self.assertEqual(cancel_mock.call_count, 1)