#!/usr/bin/env python3
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from quality.solar_term_push import generate_push_message, get_upcoming_terms


def test_get_upcoming_terms_returns_term_in_window():
    data = {'2026|立春': [2, 4, 10, 0, True]}
    terms = get_upcoming_terms(data, dt.date(2026, 2, 2), days_ahead=3)
    assert len(terms) == 1
    assert terms[0]['name'] == '立春'
    assert terms[0]['date'] == '2026-02-04'


def test_generate_push_message_contains_client_and_term():
    msg = generate_push_message('张三', '立春')
    assert '张三' in msg
    assert '立春' in msg
