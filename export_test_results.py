#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
テストを実行して結果を Excel (または CSV) に出力するスクリプト

実行方法:
    python export_test_results.py

要件:
    - openpyxl がインストールされていれば .xlsx を生成
    - 無ければ .csv を生成（Excelで開けます）
"""
import unittest
import importlib.util
import os
import sys
import traceback
from datetime import datetime

# テストモジュールのパス
BASE_DIR = os.path.dirname(__file__)
TEST_MODULE = os.path.join(BASE_DIR, 'test_instrument_analyzer.py')

# 出力先：テスト結果用ディレクトリを分離
TEST_RESULTS_DIR = os.path.join(BASE_DIR, 'test_results')
if not os.path.exists(TEST_RESULTS_DIR):
    os.makedirs(TEST_RESULTS_DIR)

timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
XLSX_PATH = os.path.join(TEST_RESULTS_DIR, f'test_results_{timestamp}.xlsx')
CSV_PATH = os.path.join(TEST_RESULTS_DIR, f'test_results_{timestamp}.csv')

# カスタム TestResult
class RecordingResult(unittest.result.TestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.records = []  # list of dicts: {class, test, status, details}
        self._start_time = datetime.now()

    def _record(self, test, status, details=''):
        test_id = test.id()  # module.Class.test
        parts = test_id.split('.')
        if len(parts) >= 3:
            test_class = parts[-2]
            test_name = parts[-1]
        else:
            test_class = parts[0]
            test_name = test_id
        self.records.append({
            'class': test_class,
            'test': test_name,
            'status': status,
            'details': details,
        })

    def addSuccess(self, test):
        super().addSuccess(test)
        self._record(test, 'PASS', '')

    def addFailure(self, test, err):
        super().addFailure(test, err)
        details = ''.join(traceback.format_exception(*err))
        self._record(test, 'FAIL', details)

    def addError(self, test, err):
        super().addError(test, err)
        details = ''.join(traceback.format_exception(*err))
        self._record(test, 'ERROR', details)

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self._record(test, 'SKIPPED', str(reason))


def run_tests_and_export():
    # モジュールをロードしてテストスイートを作成
    loader = unittest.TestLoader()
    # load by file name
    spec = importlib.util.spec_from_file_location('test_instrument_analyzer', TEST_MODULE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    suite = loader.loadTestsFromModule(module)

    # 実行
    runner = unittest.TextTestRunner(resultclass=RecordingResult, verbosity=2)
    result = runner.run(suite)

    # 出力フォーマットに整形
    rows = []
    for rec in result.records:
        rows.append([rec['class'], rec['test'], rec['status'], rec['details']])

    summary = {
        'total': result.testsRun,
        'failures': len(result.failures),
        'errors': len(result.errors),
        'skipped': len(result.skipped),
        'passed': len([r for r in result.records if r['status'] == 'PASS'])
    }

    # Try to write xlsx with openpyxl, fallback to csv
    try:
        import openpyxl
        from openpyxl import Workbook
        wb = Workbook()
        ws = wb.active
        ws.title = 'Test Results'
        ws.append(['Test Class', 'Test Name', 'Status', 'Details'])
        for r in rows:
            ws.append(r)
        # summary sheet
        ws2 = wb.create_sheet('Summary')
        ws2.append(['Total', summary['total']])
        ws2.append(['Passed', summary['passed']])
        ws2.append(['Failures', summary['failures']])
        ws2.append(['Errors', summary['errors']])
        ws2.append(['Skipped', summary['skipped']])
        wb.save(XLSX_PATH)
        print(f'Wrote Excel test results to: {XLSX_PATH}')
        return XLSX_PATH
    except Exception as e:
        # fallback to CSV
        import csv
        with open(CSV_PATH, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['Test Class', 'Test Name', 'Status', 'Details'])
            for r in rows:
                writer.writerow(r)
            writer.writerow([])
            writer.writerow(['Total', summary['total']])
            writer.writerow(['Passed', summary['passed']])
            writer.writerow(['Failures', summary['failures']])
            writer.writerow(['Errors', summary['errors']])
            writer.writerow(['Skipped', summary['skipped']])
        print(f'openpyxl not available or failed ({e}). Wrote CSV test results to: {CSV_PATH}')
        return CSV_PATH


if __name__ == '__main__':
    path = run_tests_and_export()
    print('Done. Output file:', path)
