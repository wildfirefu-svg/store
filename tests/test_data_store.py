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


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
