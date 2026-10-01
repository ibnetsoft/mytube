import unittest
from worker.codex_subtitle_translation import translate_blocks, process_one


class Runner:
    def __init__(self, response):
        self.response = response

    def _stage(self, *args):
        return self.response


class TranslationTests(unittest.TestCase):
    blocks = [{'index': 3, 'source_text': '「ありがとう」'}, {'index': 7, 'source_text': 'お鈴は笑った。'}]

    def test_preserves_source_indexes_and_accepts_reordered_response(self):
        result = translate_blocks(Runner({'translations': [
            {'id': 'b7', 'translation': '오스즈는 웃었다.'},
            {'id': 'b3', 'translation': '“고마워.”'},
        ]}), 'test', self.blocks, 'ko')
        self.assertEqual([b['index'] for b in result], [3, 7])
        self.assertEqual(result[0]['source_text'], self.blocks[0]['source_text'])
        self.assertEqual(result[0]['translated_text'], '“고마워.”')

    def test_rejects_missing_duplicate_and_empty_translations(self):
        for items in ([{'id': 'b3', 'translation': 'a'}],
                      [{'id': 'b3', 'translation': 'a'}, {'id': 'b3', 'translation': 'b'}],
                      [{'id': 'b3', 'translation': 'a'}, {'id': 'b7', 'translation': ''}]):
            with self.assertRaises(ValueError):
                translate_blocks(Runner({'translations': items}), 'test', self.blocks, 'ko')

    def test_failed_validation_never_publishes_to_project(self):
        calls = []

        class Store:
            def request(self, method, table, **kwargs):
                calls.append((table, kwargs))
                if table.startswith('rpc/claim'):
                    return ([{'id': 'test', 'source_blocks': TranslationTests.blocks, 'target_language': 'ko'}], None)
                return ([], None)

        self.assertTrue(process_one(Store(), Runner({'translations': []})))
        self.assertFalse(any(table.startswith('rpc/complete') for table, _ in calls))
        self.assertEqual(calls[-1][1]['body']['status'], 'failed')


if __name__ == '__main__':
    unittest.main()
