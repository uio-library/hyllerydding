# encoding=utf-8
from __future__ import print_function
import os
import sys
from requests import Session
import untangle
from textwrap import dedent
import yaml
from tqdm import tqdm
from datetime import datetime


def store_report(session, stream, endpoint, path, filter):
    token = None
    aggs = {}
    n = 0
    column_map = {
        'Column1': 'title',
        'Column2': 'callcode',
        'Column3': 'barcode',
        'Column4': 'process_type',
    }
    with tqdm(file=sys.stdout) as pbar:
        while True:
            if token is None:
                params = {'path': path, 'limit': 200, 'filter': filter}
            else:
                params = {'token': token}
            res = session.get(endpoint, params=params)

            res.raise_for_status()

            xml = untangle.parse(res.text.encode('utf-8'))
            if 'web_service_result' in dir(xml):
                raise RuntimeError(xml.web_service_result.errorList.error.errorMessage.cdata)

            for row in xml.report.QueryResult.ResultXml.rowset.Row:
                data = {}
                for k, v in column_map.items():
                    data[v] = ''
                    if k in dir(row):
                        data[v] = getattr(row, k).cdata
                if data['barcode'] == '':
                    continue
                if data['callcode'] == 'Unknown':
                    data['callcode'] = '?'
                if len(data['title']) > 100:
                    data['title'] = data['title'][:98] + '...'
                line = u'{barcode}\t{callcode} {title} ({process_type})\r\n'.format(**data)
                stream.write(line.encode('utf-8'))
                n += 1
                aggs[data['process_type']] = aggs.get(data['process_type'], 0) + 1
                pbar.update(1)

            if 'ResumptionToken' in dir(xml.report.QueryResult):
                token = xml.report.QueryResult.ResumptionToken.cdata

            if xml.report.QueryResult.IsFinished.cdata != 'false':
                break
    return aggs


def main():

    # Read config
    with open(os.path.join(os.path.dirname(__file__), 'config.yml')) as f:
        config = yaml.load(f)

    # HTTP session
    api_key = config['alma_api_key']  # Use read-only key
    endpoint = 'https://api-eu.hosted.exlibrisgroup.com/almaws/v1/analytics/reports'
    session = Session()
    session.headers.update({'Authorization': 'apikey ' + api_key})

    report_path = config['report_path']
    varname = config['variable']

    for fname, values in config['files'].items():

        values = ''.join(['<sawx:expr xsi:type="xsd:string">{}</sawx:expr>'.format(value) for value in values])
        report_filter = dedent(
        """<sawx:expr xsi:type="sawx:list" op="in"
             xmlns:saw="com.siebel.analytics.web/report/v1.1" 
             xmlns:sawx="com.siebel.analytics.web/expression/v1.1"
             xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" 
             xmlns:xsd="http://www.w3.org/2001/XMLSchema">
               <sawx:expr xsi:type="sawx:sqlExpression">{}</sawx:expr>
               {}
           </sawx:expr>""".format(varname, values))

        dest_path = os.path.join(config['dest']['path'], fname)
        print('Updating {}'.format(dest_path))
        with open(dest_path, 'w') as f:
            aggs = store_report(session, f, endpoint, report_path, report_filter)

        # Store stats so we can plot trends over time
        stats_path = os.path.join(config['dest']['path'], 'stats.csv')
        log_path = os.path.join(config['dest']['path'], fname + '.log')
        now = datetime.now().strftime('%Y-%m-%d')
        with open(stats_path, 'a') as f:
            with open(log_path, 'w') as f2:
                for k, v in aggs.items():
                    print(' - {}: {}'.format(k, v))
                    f.write('{},{},{},{}\n'.format(now, fname, k, v).encode('utf-8'))
                    f2.write(' - {}: {}\r\n'.format(k, v).encode('utf-8'))

main()

