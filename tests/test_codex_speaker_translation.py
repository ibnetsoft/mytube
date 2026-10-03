import inspect
import unittest
from unittest.mock import patch

from worker import codex_subtitle_translation as translation


class Runner:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def _stage(self, *args):
        self.calls.append(args)
        return self.response


class SpeakerTranslationTests(unittest.TestCase):
    blocks = [
        {'index': 3, 'source_text': 'お鈴', 'context': '若い女性。清次を待っている。'},
        {'index': 7, 'source_text': '清次', 'context': '江戸で暮らす男性。'},
    ]

    def test_transliteration_preserves_original_name_identity_and_accepts_reordered_results(self):
        runner = Runner({'translations': [
            {'id': 'b7', 'translation': '세이지'},
            {'id': 'b3', 'translation': '오스즈'},
        ]})
        heartbeat = []
        result = translation.translate_speaker_names(runner, 'speaker-test', self.blocks, 'ko',
                                                     lambda: heartbeat.append(True))
        self.assertEqual([block['index'] for block in result], [3, 7])
        self.assertEqual([block['source_text'] for block in result], ['お鈴', '清次'])
        self.assertEqual([block['translated_text'] for block in result], ['오스즈', '세이지'])
        self.assertTrue(heartbeat)
        self.assertEqual(len(runner.calls), 1)
        prompt = runner.calls[0][-1]
        self.assertIn('Korean', prompt)
        self.assertIn('transliter', prompt.lower())
        self.assertIn('untrusted', prompt.lower())
        self.assertIn('若い女性', str(runner.calls[0][2]), 'Name readings need the supplied story context')

    def test_thai_names_use_the_local_runner(self):
        runner = Runner({'translations': [{'id': 'b3', 'translation': 'โอซุสุ'}]})
        result = translation.translate_speaker_names(runner, 'speaker-test', self.blocks[:1], 'th')
        self.assertEqual(result[0]['source_text'], 'お鈴')
        self.assertEqual(result[0]['translated_text'], 'โอซุสุ')
        self.assertIn('Thai', runner.calls[0][-1])

    def test_names_across_batches_keep_every_identity_and_refresh_the_lease(self):
        blocks = [{'index': index, 'source_text': f'人物{index}'} for index in range(31)]
        batches = []

        class BatchRunner:
            def _stage(self, identity, stage, payload, prompt):
                names = payload['names']
                batches.append(names)
                return {'translations': [
                    {'id': item['id'], 'translation': f"인물{item['id'][1:]}"} for item in reversed(names)
                ]}

        heartbeats = []
        result = translation.translate_speaker_names(BatchRunner(), 'speaker-test', blocks, 'ko',
                                                     lambda: heartbeats.append(True))
        self.assertEqual([len(batch) for batch in batches], [30, 1])
        self.assertEqual(len(heartbeats), 2)
        self.assertEqual([block['source_text'] for block in result], [block['source_text'] for block in blocks])
        self.assertEqual([block['translated_text'] for block in result], [f'인물{index}' for index in range(31)])

    def test_unsupported_name_languages_never_run_codex(self):
        for language in ('en', 'ja', '', None):
            with self.subTest(language=language):
                runner = Runner({})
                with self.assertRaises(ValueError):
                    translation.translate_speaker_names(runner, 'speaker-test', self.blocks, language)
                self.assertEqual(runner.calls, [])

    def test_missing_duplicate_unknown_and_empty_results_are_rejected(self):
        invalid_responses = [
            None,
            {},
            {'translations': [{'id': 'b3', 'translation': '오스즈'}]},
            {'translations': [{'id': 'b3', 'translation': '오스즈'}, {'id': 'b3', 'translation': '세이지'}]},
            {'translations': [{'id': 'b3', 'translation': '오스즈'}, {'id': 'b99', 'translation': '세이지'}]},
            {'translations': [{'id': 'b3', 'translation': '오스즈'}, {'id': 'b7', 'translation': '  '}]},
        ]
        for response in invalid_responses:
            with self.subTest(response=response):
                with self.assertRaises(ValueError):
                    translation.translate_speaker_names(Runner(response), 'speaker-test', self.blocks, 'ko')

    def store_for(self, kind):
        calls = []
        job = {'id': 'speaker-test', 'source_blocks': self.blocks, 'target_language': 'ko'}
        if kind is not None:
            job['translation_kind'] = kind

        class Store:
            def request(self, method, table, **kwargs):
                calls.append((method, table, kwargs))
                if table == 'rpc/claim_std_subtitle_translation':
                    return [job], None
                return [], None

        return Store(), calls

    def test_process_one_dispatches_speaker_jobs_and_publishes_validated_results(self):
        store, calls = self.store_for('speaker_names')
        expected = [{**block, 'translated_text': name} for block, name in zip(self.blocks, ['오스즈', '세이지'])]
        with patch.object(translation, 'translate_speaker_names', return_value=expected) as speaker, \
                patch.object(translation, 'translate_blocks') as subtitle:
            runner = Runner({})
            self.assertTrue(translation.process_one(store, runner))
        subtitle.assert_not_called()
        self.assertEqual(speaker.call_args.args[:4], (runner, 'speaker-test', self.blocks, 'ko'))
        completion = [kwargs['body'] for _, table, kwargs in calls if table == 'rpc/complete_std_subtitle_translation']
        self.assertEqual(completion, [{'job_id': 'speaker-test', 'translated_blocks': expected}])

    def test_process_one_keeps_legacy_subtitle_jobs_on_the_subtitle_path(self):
        for kind in (None, 'subtitles'):
            with self.subTest(kind=kind):
                store, _ = self.store_for(kind)
                with patch.object(translation, 'translate_speaker_names') as speaker, \
                        patch.object(translation, 'translate_blocks', return_value=[]) as subtitle:
                    self.assertTrue(translation.process_one(store, Runner({})))
                speaker.assert_not_called()
                subtitle.assert_called_once()

    def test_invalid_speaker_results_fail_without_publishing_to_the_project(self):
        store, calls = self.store_for('speaker_names')
        self.assertTrue(translation.process_one(store, Runner({'translations': []})))
        self.assertFalse(any(table == 'rpc/complete_std_subtitle_translation' for _, table, _ in calls))
        self.assertEqual(calls[-1][2]['body']['status'], 'failed')
        self.assertNotIn('若い女性', str(calls[-1][2]['body']))

    def test_worker_does_not_use_cloud_model_apis(self):
        source = inspect.getsource(translation)
        for forbidden in ('OPENAI_API_KEY', 'GEMINI_API_KEY', 'api.openai.com',
                          'generativelanguage.googleapis', 'import openai', 'google.generativeai'):
            self.assertNotIn(forbidden, source)


if __name__ == '__main__':
    unittest.main()
