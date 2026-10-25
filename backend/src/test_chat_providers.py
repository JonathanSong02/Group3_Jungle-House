"""Provider serialization and context configuration; HTTP is always mocked."""
import os
import unittest
from unittest.mock import MagicMock, patch

import ai_provider_service as provider
from chat_memory import ChatError


class ProviderChatTests(unittest.TestCase):
    def test_output_budget_is_sent_to_each_provider(self):
        for name in ('gemini', 'openai', 'deepseek', 'anthropic'):
            with self.subTest(provider=name):
                response = MagicMock()
                response.json.return_value = {
                    'candidates': [{'content': {'parts': [{'text': 'ok'}]}}],
                    'choices': [{'message': {'content': 'ok'}}], 'content': [{'text': 'ok'}],
                }
                with patch.object(provider.requests, 'post', return_value=response) as post:
                    result = provider.call_ai_provider('UNTRUSTED history and current KB', name, 'mock-model', 'mock-key', max_output_tokens=1024)
                self.assertEqual(result, 'ok')
                payload = post.call_args.kwargs['json']
                if name == 'gemini':
                    self.assertEqual(payload['generationConfig']['maxOutputTokens'], 1024)
                    self.assertIn('history', payload['contents'][0]['parts'][0]['text'])
                else:
                    key = 'max_completion_tokens' if name == 'openai' else 'max_tokens'
                    self.assertEqual(payload[key], 1024)
                    self.assertIn('history', payload['messages'][0]['content'])

    def configured(self, env):
        connection = MagicMock()
        connection.cursor.return_value.fetchone.return_value = {'provider': 'openai', 'model_name': 'mock-model', 'encrypted_api_key': 'mock'}
        return patch.dict(os.environ, env), patch.object(provider, 'get_db_connection', return_value=connection), patch.object(provider, 'decrypt_api_key', return_value='mock-key')

    def test_model_snapshot_context_budget_and_unknown_model_requires_configuration(self):
        env, db, decrypt = self.configured({'CHAT_CONTEXT_OPENAI_MOCK_MODEL': '8192', 'CHAT_WORKING_TOKENS': '6000', 'CHAT_OUTPUT_TOKENS': '1024'})
        with env, db, decrypt:
            generate, context, output = provider.chat_generator()
        self.assertEqual((context, output), (6000, 1024))
        with patch.object(provider, 'call_ai_provider', return_value='mock') as call:
            self.assertEqual(generate('small prompt'), 'mock')
            self.assertEqual(call.call_args.kwargs['max_output_tokens'], 1024)
            with self.assertRaises(RuntimeError):
                generate('too big ' * 1000)
        env, db, decrypt = self.configured({'CHAT_CONTEXT_OPENAI_MOCK_MODEL': ''})
        with env, db, decrypt, self.assertRaises(ChatError) as error:
            provider.chat_generator()
        self.assertIn('CHAT_CONTEXT_OPENAI_MOCK_MODEL', str(error.exception))
