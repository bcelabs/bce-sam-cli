'use strict';

const index = require('../../index.js');
const chai = require('chai');
const expect = chai.expect;
var event, context;

{% if cookiecutter.runtime == 'nodejs6.11' or cookiecutter.runtime == 'nodejs4.3' %}
describe('Tests Handler', function () {
    it('verifies successful response', function (done) {
        index.handler(event, context, function (err, result) {
            try {
                expect(result).to.be.an('object');
                expect(result.statusCode).to.equal(200);
                expect(result.body).to.be.an('string');

                let response = JSON.parse(result.body);

                expect(response).to.be.an('object');
                expect(response.message).to.be.equal("hello world");                
                done();
            } catch (e) {
                done(e);
            }
        });
    });
});
{% else %}
describe('Tests index', function () {
    it('verifies successful response', async () => {
        const result = await index.handler(event, context, (err, result) => {
            expect(result).to.be.an('object');
            expect(result.statusCode).to.equal(200);
            expect(result.body).to.be.an('string');

            let response = JSON.parse(result.body);

            expect(response).to.be.an('object');
            expect(response.message).to.be.equal("hello world");            
        });
    });
});
{% endif %}
