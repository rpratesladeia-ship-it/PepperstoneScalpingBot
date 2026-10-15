'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { safeTokenEqual, validateSignal, parseModelDecision, extractOutputText, requestOpenAIFilter } = require('../server');

const valid = {
  type: 'analyze', requestId: 'request-12345678', token: 'secret',
  symbol: 'EURUSD', side: 'buy', timeframe: 'Minute',
  fastEma: 1.1, slowEma: 1.09, rsi: 58, atrPips: 5,
  spreadPips: 0.4, stopLossPips: 7.5, takeProfitPips: 15
};

test('token comparison accepts only exact non-empty tokens', () => {
  assert.equal(safeTokenEqual('secret', 'secret'), true);
  assert.equal(safeTokenEqual('wrong', 'secret'), false);
  assert.equal(safeTokenEqual('', 'secret'), false);
});

test('valid signal passes schema validation', () => {
  assert.equal(validateSignal(valid), true);
});

test('invalid side and non-finite values are rejected', () => {
  assert.equal(validateSignal({ ...valid, side: 'hold' }), false);
  assert.equal(validateSignal({ ...valid, rsi: NaN }), false);
});

test('decision parser requires strict fields and bounded confidence', () => {
  assert.deepEqual(parseModelDecision('{"allow":true,"confidence":0.8,"reason":"clear"}'),
    { allow: true, confidence: 0.8, reason: 'clear' });
  assert.equal(parseModelDecision('{"allow":true,"confidence":9,"reason":"bad"}'), null);
  assert.equal(parseModelDecision('not json'), null);
});

test('extract output text reads Responses API message content', () => {
  assert.equal(extractOutputText({ output: [{ type: 'message', content: [{ type: 'output_text', text: '{"allow":false}' }] }] }),
    '{"allow":false}');
});

test('OpenAI failure cannot return an approval', async () => {
  await assert.rejects(
    requestOpenAIFilter(valid, { OPENAI_API_KEY: 'x', OPENAI_MODEL: 'test' },
      async () => ({ ok: false, status: 500 })),
    /HTTP 500/
  );
});
