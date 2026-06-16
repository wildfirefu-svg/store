#!/usr/bin/env python3
"""Tests for data_store.py — SQLite persistence layer."""
import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import data_store


class TestCharts:
    def test_save_and_get(self):
        cid = 'test_chart_save_001'
        data_store.save_chart(cid, '测试命主', {'year': 2000, 'month': 1}, {'four_pillars': {'year': {'gan': '甲'}}})
        chart = data_store.get_chart(cid)
        assert chart is not None
        assert chart['name'] == '测试命主'
        assert chart['chart_data']['four_pillars']['year']['gan'] == '甲'
        data_store.delete_chart(cid)

    def test_list_charts(self):
        cid = 'test_chart_list_001'
        data_store.save_chart(cid, '列表测试', {}, {})
        charts = data_store.list_charts()
        assert any(c['chart_id'] == cid for c in charts)
        data_store.delete_chart(cid)

    def test_update_chart(self):
        cid = 'test_chart_update_001'
        data_store.save_chart(cid, '原名', {}, {})
        data_store.save_chart(cid, '新名', {'year': 2020}, {'updated': True})
        chart = data_store.get_chart(cid)
        assert chart['name'] == '新名'
        assert chart['birth_info']['year'] == 2020
        data_store.delete_chart(cid)

    def test_delete_chart_cascades(self):
        cid = 'test_chart_cascade_001'
        data_store.save_chart(cid, '级联测试', {}, {})
        data_store.append_chat_message(cid, 'user', '消息一')
        data_store.append_chat_message(cid, 'agent', '消息二', '工具')
        data_store.save_report(cid, 'overview', '# 总览报告')
        data_store.save_report(cid, 'wealth', '# 财运报告')

        assert len(data_store.get_chat_history(cid)) == 2
        assert len(data_store.get_reports(cid)) == 2

        data_store.delete_chart(cid)
        assert data_store.get_chart(cid) is None
        assert len(data_store.get_chat_history(cid)) == 0
        assert len(data_store.get_reports(cid)) == 0


class TestChatHistory:
    def test_append_and_get(self):
        cid = 'test_chat_append_001'
        data_store.save_chart(cid, '聊天测试', {}, {})
        data_store.append_chat_message(cid, 'user', '你好')
        data_store.append_chat_message(cid, 'agent', '回复', '四合出分析')
        msgs = data_store.get_chat_history(cid)
        assert len(msgs) == 2
        assert msgs[0]['role'] == 'user'
        assert msgs[0]['text'] == '你好'
        assert msgs[1]['role'] == 'agent'
        assert msgs[1]['tool'] == '四合出分析'
        data_store.delete_chart(cid)

    def test_empty_history(self):
        cid = 'test_chat_empty_001'
        data_store.save_chart(cid, '空历史', {}, {})
        msgs = data_store.get_chat_history(cid)
        assert msgs == []
        data_store.delete_chart(cid)

    def test_history_limit(self):
        cid = 'test_chat_limit_001'
        data_store.save_chart(cid, '限制测试', {}, {})
        for i in range(600):
            data_store.append_chat_message(cid, 'user', f'msg_{i}')
        msgs = data_store.get_chat_history(cid)
        assert len(msgs) <= 500
        data_store.delete_chart(cid)


class TestReports:
    def test_save_and_get(self):
        cid = 'test_report_save_001'
        data_store.save_chart(cid, '报告测试', {}, {})
        data_store.save_report(cid, 'wealth', '# 财运分析\n内容')
        data_store.save_report(cid, 'health', '# 健康分析\n内容')
        reports = data_store.get_reports(cid)
        assert 'wealth' in reports
        assert 'health' in reports
        assert '财运分析' in reports['wealth']
        data_store.delete_chart(cid)

    def test_update_report(self):
        cid = 'test_report_update_001'
        data_store.save_chart(cid, '更新测试', {}, {})
        data_store.save_report(cid, 'overview', '# 第一版')
        data_store.save_report(cid, 'overview', '# 第二版')
        reports = data_store.get_reports(cid)
        assert '第二版' in reports['overview']
        data_store.delete_chart(cid)

    def test_empty_reports(self):
        cid = 'test_report_empty_001'
        data_store.save_chart(cid, '空报告', {}, {})
        reports = data_store.get_reports(cid)
        assert reports == {}
        data_store.delete_chart(cid)



class TestClients:
    def test_client_crud(self):
        client = data_store.create_client({
            'name': '客户测试',
            'gender': 'male',
            'birth_year': 1990,
            'birth_month': 5,
            'birth_day': 12,
            'birth_hour': 8,
            'tags': ['事业'],
            'notes': '初次咨询',
        })
        try:
            assert client['id']
            assert client['name'] == '客户测试'
            assert client['tags'] == ['事业']

            clients = data_store.list_clients(search='客户测试')
            assert any(c['id'] == client['id'] for c in clients)

            fetched = data_store.get_client(client['id'])
            assert fetched['name'] == '客户测试'

            updated = data_store.update_client(client['id'], {'name': '客户测试更新', 'tags': ['事业', 'VIP']})
            assert updated['name'] == '客户测试更新'
            assert updated['tags'] == ['事业', 'VIP']
        finally:
            data_store.delete_client(client['id'])
            assert data_store.get_client(client['id']) is None

    def test_client_chart_link(self):
        cid = 'test_client_chart_001'
        data_store.save_chart(cid, '关联命盘', {}, {'day_master': {'gan': '甲'}})
        client = data_store.create_client({'name': '关联客户'})
        try:
            data_store.link_client_chart(client['id'], cid)
            charts = data_store.list_client_charts(client['id'])
            assert any(c['chart_id'] == cid for c in charts)
            data_store.unlink_client_chart(client['id'], cid)
            charts = data_store.list_client_charts(client['id'])
            assert all(c['chart_id'] != cid for c in charts)
        finally:
            data_store.delete_client(client['id'])
            data_store.delete_chart(cid)


class TestAnalysesAndFeedback:
    def test_save_and_list_analysis(self):
        cid = 'test_analysis_chart_001'
        data_store.save_chart(cid, '分析命盘', {}, {'day_master': {'gan': '乙'}})
        client = data_store.create_client({'name': '分析客户'})
        try:
            data_store.link_client_chart(client['id'], cid)
            analysis = data_store.save_analysis(
                client_id=client['id'],
                chart_id=cid,
                analysis_type='chat',
                topic='sihechu',
                question='请分析事业',
                ai_text='## 核心判断\n测试分析',
                structured_summary={'score': 0.8},
                report_tab='sihechu',
            )

            fetched = data_store.get_analysis(analysis['id'])
            assert fetched['question'] == '请分析事业'
            assert fetched['structured_summary']['score'] == 0.8

            by_client = data_store.list_client_analyses(client['id'])
            by_chart = data_store.list_chart_analyses(cid)
            assert any(a['id'] == analysis['id'] for a in by_client)
            assert any(a['id'] == analysis['id'] for a in by_chart)
        finally:
            data_store.delete_client(client['id'])
            data_store.delete_chart(cid)

    def test_save_feedback_and_stats(self):
        cid = 'test_feedback_chart_001'
        data_store.save_chart(cid, '反馈命盘', {}, {'day_master': {'gan': '丙'}})
        client = data_store.create_client({'name': '反馈客户'})
        try:
            analysis = data_store.save_analysis(
                client_id=client['id'],
                chart_id=cid,
                analysis_type='chat',
                topic='career',
                question='事业如何',
                ai_text='事业判断',
            )
            feedback = data_store.save_feedback(
                analysis_id=analysis['id'],
                dimension='career',
                judgment_text='适合专业路线',
                is_accurate=True,
                user_comment='准确',
            )
            assert feedback['id']
            stats = data_store.get_feedback_stats()
            assert 'career' in stats['dimension_accuracy']
            assert stats['dimension_accuracy']['career']['total'] >= 1
        finally:
            data_store.delete_client(client['id'])
            data_store.delete_chart(cid)


class TestModelOutputs:
    def test_save_and_get_model_output(self):
        cid = 'test_model_output_chart_001'
        data_store.save_chart(cid, '模型输出命盘', {}, {'day_master': {'gan': '戊'}})
        client = data_store.create_client({'name': '模型输出客户'})
        try:
            analysis = data_store.save_analysis(
                client_id=client['id'],
                chart_id=cid,
                analysis_type='chat',
                topic='career',
                question='请分析事业',
                ai_text='事业分析',
            )
            payload = {
                'analysis_id': analysis['id'],
                'chart_id': cid,
                'client_id': client['id'],
                'provider': 'deepseek',
                'model': 'deepseek-v4-pro',
                'method': 'structured',
                'prompt_version': 'srp_v1',
                'reasoning_protocol': 'xuanjizi_srp_v1',
                'domain': 'career',
                'question': '请分析事业',
                'input_hash': 'abc123',
                'raw_prompt': 'prompt text',
                'raw_output': 'answer text',
                'parsed_answer': None,
                'structured_reasoning_json': {'confidence': 0.7},
                'latency_ms': 1234,
                'token_estimate': 1000,
                'cost_estimate': 0.01,
            }
            saved = data_store.save_model_output(**payload)
            assert saved['id']
            loaded = data_store.get_model_output(saved['id'])
            assert loaded['model'] == 'deepseek-v4-pro'
            assert loaded['structured_reasoning_json']['confidence'] == 0.7
            assert loaded['client_id'] == client['id']
        finally:
            data_store.delete_client(client['id'])
            data_store.delete_chart(cid)

    def test_list_model_outputs_limit_is_defensive(self):
        assert isinstance(data_store.list_model_outputs(limit=None), list)
        assert isinstance(data_store.list_model_outputs(limit='bad'), list)
        assert isinstance(data_store.list_model_outputs(limit=999), list)
        assert isinstance(data_store.list_model_outputs(limit=0), list)

    def test_list_model_outputs_for_chart(self):
        cid = 'test_model_output_chart_002'
        data_store.save_chart(cid, '模型输出列表', {}, {'day_master': {'gan': '己'}})
        try:
            saved = data_store.save_model_output(
                chart_id=cid,
                provider='deepseek',
                model='deepseek-v4-pro',
                method='structured',
                prompt_version='srp_v1',
                reasoning_protocol='xuanjizi_srp_v1',
                domain='wealth',
                question='财运如何',
                raw_output='财运回答',
                structured_reasoning_json={'domain': 'wealth'},
            )
            items = data_store.list_model_outputs(chart_id=cid)
            assert any(x['id'] == saved['id'] for x in items)
        finally:
            data_store.delete_chart(cid)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])


class TestBenchmarkCases:
    def test_save_and_get_benchmark_case(self):
        payload = {
            'id': 'case-test-001',
            'source': 'baziqa_mini',
            'person_id': 'p001',
            'name': '命主测试',
            'profile_json': '{"gender": "male", "birth_year": 1990}',
            'chart_input_json': '{"year": 1990, "month": 3}',
            'chart_result_json': '{"sun": "甲"}',
            'verified_events_json': '[]',
            'anonymized': 1,
            'license_note': 'Internal',
        }
        saved = data_store.save_benchmark_case(**payload)
        assert saved['id'] == 'case-test-001'
        assert saved['source'] == 'baziqa_mini'
        assert saved['anonymized'] == 1
        loaded = data_store.get_benchmark_case('case-test-001')
        assert loaded is not None
        assert loaded['name'] == '命主测试'

    def test_list_benchmark_cases(self):
        saved = data_store.save_benchmark_case(
            id='case-list-001',
            source='internal',
            person_id='p002',
            name='列表测试',
            profile_json='{}',
            chart_input_json='{}',
            chart_result_json='{}',
        )
        cases = data_store.list_benchmark_cases()
        assert any(c['id'] == 'case-list-001' for c in cases)
        cases_filtered = data_store.list_benchmark_cases(source='internal')
        assert any(c['id'] == 'case-list-001' for c in cases_filtered)


class TestBenchmarkQuestions:
    def test_save_and_get_benchmark_question(self):
        data_store.save_benchmark_case(
            id='case-q-test-001',
            source='baziqa_mini',
            person_id='p003',
            name='问题测试',
            profile_json='{}',
            chart_input_json='{}',
            chart_result_json='{}',
        )
        payload = {
            'id': 'q-test-001',
            'case_id': 'case-q-test-001',
            'domain': 'career',
            'question': '事业发展方向？',
            'options_json': '["A. 选项1", "B. 选项2", "C. 选项3", "D. 选项4"]',
            'answer': 'A',
            'expected_evidence_json': '["官星有力"]',
            'difficulty': 'medium',
        }
        saved = data_store.save_benchmark_question(**payload)
        assert saved['id'] == 'q-test-001'
        assert saved['domain'] == 'career'
        loaded = data_store.get_benchmark_question('q-test-001')
        assert loaded is not None
        assert loaded['answer'] == 'A'

    def test_list_benchmark_questions(self):
        data_store.save_benchmark_case(
            id='case-q-list-001',
            source='internal',
            person_id='p004',
            name='列表问题测试',
            profile_json='{}',
            chart_input_json='{}',
            chart_result_json='{}',
        )
        data_store.save_benchmark_question(
            id='q-list-001',
            case_id='case-q-list-001',
            domain='wealth',
            question='财运如何？',
            options_json='["A", "B", "C", "D"]',
            answer='B',
            expected_evidence_json='[]',
            difficulty='easy',
        )
        questions = data_store.list_benchmark_questions(case_id='case-q-list-001')
        assert any(q['id'] == 'q-list-001' for q in questions)


class TestBenchmarkRuns:
    def test_save_and_get_benchmark_run(self):
        payload = {
            'id': 'run-test-001',
            'dataset': 'baziqa_mini_v1',
            'provider': 'deepseek',
            'model': 'deepseek-v4-pro',
            'method': 'structured',
            'prompt_version': 'srp_v1',
            'reasoning_protocol': 'xuanjizi_srp_v1',
            'n_cases': 15,
            'n_questions': 15,
            'accuracy': 0.67,
            'evidence_score': 0.72,
            'stability_score': 0.85,
            'safety_score': 0.95,
            'report_path': 'benchmark/outputs/run_test_001.md',
        }
        saved = data_store.save_benchmark_run(**payload)
        assert saved['accuracy'] == 0.67
        assert saved['evidence_score'] == 0.72
        loaded = data_store.get_benchmark_run('run-test-001')
        assert loaded is not None
        assert loaded['model'] == 'deepseek-v4-pro'
        assert loaded['stability_score'] == 0.85

    def test_list_benchmark_runs(self):
        data_store.save_benchmark_run(
            id='run-list-001',
            dataset='baziqa_mini_v1',
            provider='deepseek',
            model='deepseek-v4-pro',
            method='structured',
            n_cases=5,
            n_questions=5,
            accuracy=0.8,
        )
        runs = data_store.list_benchmark_runs()
        assert any(r['id'] == 'run-list-001' for r in runs)
        runs_filtered = data_store.list_benchmark_runs(dataset='baziqa_mini_v1')
        assert any(r['id'] == 'run-list-001' for r in runs_filtered)
