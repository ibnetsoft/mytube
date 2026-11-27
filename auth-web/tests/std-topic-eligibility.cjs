const {test}=require('node:test'),assert=require('node:assert/strict'),load=require('./load-ts-module.cjs');
const {isAvailablePendingTopic,mergeAvailableTopics}=load('lib/stdTopicEligibility.ts');
const pending={status:'pending',assigned_at:null};
test('unreserved pending topics remain available',()=>{assert.equal(isAvailablePendingTopic({...pending,assigned_employee_email:null},'user@example.com'),true);assert.equal(isAvailablePendingTopic({...pending,assigned_employee_email:''},'user@example.com'),true)});
test('a reserved pending topic is available only to its owner',()=>{const topic={...pending,assigned_employee_email:'Owner@example.com'};assert.equal(isAvailablePendingTopic(topic,'owner@example.com'),true);assert.equal(isAvailablePendingTopic(topic,'other@example.com'),false);assert.equal(isAvailablePendingTopic(topic),false)});
test('claimed or timestamp-assigned topics cannot be claimed again',()=>{assert.equal(isAvailablePendingTopic({...pending,status:'assigned'},'owner@example.com'),false);assert.equal(isAvailablePendingTopic({...pending,assigned_at:'2026-11-07T00:00:00Z',assigned_employee_email:'owner@example.com'},'owner@example.com'),false)});
test('owned reservations appear first without duplicates and respect the limit',()=>{assert.deepEqual(mergeAvailableTopics([{id:3433}],[{id:3427},{id:3433},{id:3388}],2),[{id:3433},{id:3427}])});
