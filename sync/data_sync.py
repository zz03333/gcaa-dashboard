#!/usr/bin/env python3
"""
GCAA 社群分析 - 資料同步腳本
從 Google Sheets 讀取 raw_posts + raw_post_insights，生成 JSON 檔案供前端使用
"""

import json
import os
from datetime import datetime, timedelta
from collections import defaultdict
from google.oauth2 import service_account
from googleapiclient.discovery import build

# 設定
SPREADSHEET_ID = '1HJXQrlB0eYJsHmioLMNfCKV_OXHqqgwtwRtO9s5qbB0'
SERVICE_ACCOUNT_FILE = os.path.join(os.path.dirname(__file__), '..', 'esg-reports-collection-9661012923ed.json')
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), '..', 'public', 'data')

# Sheets 設定
SHEETS = {
    'raw_posts': 'raw_posts',
    'raw_insights': 'raw_post_insights'
}

def get_sheets_service():
    """建立 Google Sheets API 連線"""
    credentials = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE,
        scopes=['https://www.googleapis.com/auth/spreadsheets.readonly']
    )
    return build('sheets', 'v4', credentials=credentials)

def fetch_sheet_data(service, sheet_name):
    """從 Google Sheets 讀取資料"""
    result = service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=sheet_name
    ).execute()

    values = result.get('values', [])
    if len(values) < 2:
        return []

    headers = values[0]
    data = []
    for row in values[1:]:
        obj = {}
        for i, header in enumerate(headers):
            obj[header] = row[i] if i < len(row) else ''
        data.append(obj)

    return data

def parse_datetime(date_str):
    """解析日期時間字串"""
    if not date_str:
        return None
    try:
        # 嘗試多種格式
        for fmt in ['%Y-%m-%d %H:%M:%S', '%Y/%m/%d %H:%M:%S', '%Y-%m-%d', '%Y/%m/%d']:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue
        return None
    except Exception:
        return None

def parse_int(value):
    """安全解析整數"""
    if not value:
        return 0
    try:
        # 移除逗號 (例如 "52,143" -> 52143)
        return int(str(value).replace(',', '').replace(' ', ''))
    except (ValueError, TypeError):
        return 0

def parse_float(value):
    """安全解析浮點數"""
    if not value:
        return 0.0
    try:
        return float(str(value).replace(',', '').replace(' ', ''))
    except (ValueError, TypeError):
        return 0.0

def join_data(raw_posts, raw_insights):
    """合併 raw_posts 和 raw_insights 資料"""
    # 建立 insights lookup (by Post ID)
    insights_map = {}
    for insight in raw_insights:
        post_id = insight.get('Post ID', '')
        if post_id:
            insights_map[post_id] = insight

    posts = []
    for post in raw_posts:
        post_id = post.get('Post ID', '')
        if not post_id:
            continue

        insight = insights_map.get(post_id, {})

        # 基本資訊
        published_at = parse_datetime(post.get('發布時間 (GMT+8)', ''))
        content = post.get('內容', '')

        # 互動指標
        likes = parse_int(insight.get('讚數', 0))
        comments = parse_int(insight.get('留言數', 0))
        shares = parse_int(insight.get('分享數', 0))
        clicks = parse_int(insight.get('點擊數', 0))
        reach = parse_int(insight.get('觸及人數', 0))
        video_views = parse_int(insight.get('影片觀看', 0))

        # 表情反應
        reactions = {
            'like': parse_int(insight.get('讚', 0)),
            'love': parse_int(insight.get('愛心', 0)),
            'wow': parse_int(insight.get('哇', 0)),
            'haha': parse_int(insight.get('哈哈', 0)),
            'sad': parse_int(insight.get('嗚嗚', 0)),
            'angry': parse_int(insight.get('怒', 0))
        }

        # 計算衍生指標
        total_engagement = likes + comments + shares
        engagement_rate = (total_engagement / reach * 100) if reach > 0 else 0
        share_rate = (shares / reach * 100) if reach > 0 else 0

        # 解析標籤
        hashtags_str = post.get('標籤 (Hashtag)', '') or post.get('標籤', '')
        hashtags = [h.strip() for h in hashtags_str.split(',') if h.strip()] if hashtags_str else []

        posts.append({
            'id': post_id,
            'publishedAt': published_at.isoformat() if published_at else None,
            'content': content,
            'contentPreview': content[:80] + '...' if len(content) > 80 else content,
            'hashtags': hashtags,
            'actionType': post.get('行動', '') or '其他',
            'topic': post.get('議題', '') or '其他',
            'mediaType': post.get('媒體類型', '') or '未知',
            'permalink': post.get('連結', '') or insight.get('貼文連結', ''),
            'metrics': {
                'likes': likes,
                'comments': comments,
                'shares': shares,
                'clicks': clicks,
                'reach': reach,
                'videoViews': video_views,
                'reactions': reactions
            },
            'computed': {
                'engagementRate': round(engagement_rate, 2),
                'totalEngagement': total_engagement,
                'shareRate': round(share_rate, 2)
            }
        })

    # 按發布時間排序 (新到舊)
    posts.sort(key=lambda x: x['publishedAt'] or '', reverse=True)

    return posts

def generate_daily_data(posts):
    """生成每日聚合資料"""
    daily_map = defaultdict(lambda: {
        'postCount': 0,
        'totalReach': 0,
        'totalEngagement': 0,
        'totalShares': 0,
        'totalClicks': 0,
        'engagementRates': []
    })

    for post in posts:
        if not post['publishedAt']:
            continue

        date = post['publishedAt'][:10]  # YYYY-MM-DD
        daily = daily_map[date]

        daily['postCount'] += 1
        daily['totalReach'] += post['metrics']['reach']
        daily['totalEngagement'] += post['computed']['totalEngagement']
        daily['totalShares'] += post['metrics']['shares']
        daily['totalClicks'] += post['metrics']['clicks']
        if post['computed']['engagementRate'] > 0:
            daily['engagementRates'].append(post['computed']['engagementRate'])

    daily_data = []
    for date, data in sorted(daily_map.items(), reverse=True):
        avg_er = sum(data['engagementRates']) / len(data['engagementRates']) if data['engagementRates'] else 0
        daily_data.append({
            'date': date,
            'postCount': data['postCount'],
            'totalReach': data['totalReach'],
            'totalEngagement': data['totalEngagement'],
            'avgEngagementRate': round(avg_er, 2),
            'totalShares': data['totalShares'],
            'totalClicks': data['totalClicks']
        })

    return daily_data

def generate_stats(posts):
    """生成統計摘要"""
    # 按行動類型分組
    by_action = defaultdict(lambda: {'count': 0, 'totalER': 0, 'totalReach': 0})
    for post in posts:
        action = post['actionType']
        by_action[action]['count'] += 1
        by_action[action]['totalER'] += post['computed']['engagementRate']
        by_action[action]['totalReach'] += post['metrics']['reach']

    action_stats = []
    for name, data in sorted(by_action.items(), key=lambda x: -x[1]['count']):
        action_stats.append({
            'name': name,
            'count': data['count'],
            'avgER': round(data['totalER'] / data['count'], 2) if data['count'] > 0 else 0,
            'avgReach': round(data['totalReach'] / data['count']) if data['count'] > 0 else 0
        })

    # 按議題分組
    by_topic = defaultdict(lambda: {'count': 0, 'totalER': 0, 'totalReach': 0})
    for post in posts:
        topic = post['topic']
        by_topic[topic]['count'] += 1
        by_topic[topic]['totalER'] += post['computed']['engagementRate']
        by_topic[topic]['totalReach'] += post['metrics']['reach']

    topic_stats = []
    for name, data in sorted(by_topic.items(), key=lambda x: -x[1]['count']):
        topic_stats.append({
            'name': name,
            'count': data['count'],
            'avgER': round(data['totalER'] / data['count'], 2) if data['count'] > 0 else 0,
            'avgReach': round(data['totalReach'] / data['count']) if data['count'] > 0 else 0
        })

    # 按小時分組
    by_hour = defaultdict(lambda: {'count': 0, 'totalER': 0})
    for post in posts:
        if not post['publishedAt']:
            continue
        try:
            hour = int(post['publishedAt'][11:13])
            by_hour[hour]['count'] += 1
            by_hour[hour]['totalER'] += post['computed']['engagementRate']
        except (ValueError, IndexError):
            continue

    hour_stats = []
    for hour in range(24):
        data = by_hour[hour]
        hour_stats.append({
            'hour': hour,
            'label': f'{hour:02d}:00',
            'count': data['count'],
            'avgER': round(data['totalER'] / data['count'], 2) if data['count'] > 0 else 0
        })

    # 按星期分組
    weekday_names = ['週一', '週二', '週三', '週四', '週五', '週六', '週日']
    by_weekday = defaultdict(lambda: {'count': 0, 'totalER': 0})
    for post in posts:
        if not post['publishedAt']:
            continue
        try:
            dt = datetime.fromisoformat(post['publishedAt'])
            weekday = dt.weekday()
            by_weekday[weekday]['count'] += 1
            by_weekday[weekday]['totalER'] += post['computed']['engagementRate']
        except (ValueError, TypeError):
            continue

    weekday_stats = []
    for i in range(7):
        data = by_weekday[i]
        weekday_stats.append({
            'weekday': i,
            'name': weekday_names[i],
            'count': data['count'],
            'avgER': round(data['totalER'] / data['count'], 2) if data['count'] > 0 else 0
        })

    # 時段熱力圖 (星期 x 小時)
    heatmap = []
    by_weekday_hour = defaultdict(lambda: {'count': 0, 'totalER': 0})
    for post in posts:
        if not post['publishedAt']:
            continue
        try:
            dt = datetime.fromisoformat(post['publishedAt'])
            key = (dt.weekday(), dt.hour)
            by_weekday_hour[key]['count'] += 1
            by_weekday_hour[key]['totalER'] += post['computed']['engagementRate']
        except (ValueError, TypeError):
            continue

    for weekday in range(7):
        for hour in range(24):
            data = by_weekday_hour[(weekday, hour)]
            heatmap.append({
                'weekday': weekday,
                'weekdayName': weekday_names[weekday],
                'hour': hour,
                'count': data['count'],
                'avgER': round(data['totalER'] / data['count'], 2) if data['count'] > 0 else 0
            })

    return {
        'lastUpdated': datetime.now().isoformat(),
        'totalPosts': len(posts),
        'byActionType': action_stats,
        'byTopic': topic_stats,
        'byHour': hour_stats,
        'byDayOfWeek': weekday_stats,
        'heatmap': heatmap
    }

def main():
    print('GCAA 社群分析 - 資料同步開始')
    print(f'Service Account: {SERVICE_ACCOUNT_FILE}')
    print(f'Spreadsheet ID: {SPREADSHEET_ID}')

    # 確保輸出目錄存在
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # 連接 Google Sheets
    print('\n連接 Google Sheets...')
    service = get_sheets_service()

    # 讀取資料
    print('讀取 raw_posts...')
    raw_posts = fetch_sheet_data(service, SHEETS['raw_posts'])
    print(f'  - {len(raw_posts)} 筆貼文')

    print('讀取 raw_post_insights...')
    raw_insights = fetch_sheet_data(service, SHEETS['raw_insights'])
    print(f'  - {len(raw_insights)} 筆 insights')

    # 合併資料
    print('\n處理資料...')
    posts = join_data(raw_posts, raw_insights)
    print(f'  - 合併後: {len(posts)} 筆貼文')

    # 生成聚合資料
    daily = generate_daily_data(posts)
    print(f'  - 每日資料: {len(daily)} 天')

    stats = generate_stats(posts)
    print(f'  - 行動類型: {len(stats["byActionType"])} 種')
    print(f'  - 議題: {len(stats["byTopic"])} 種')

    # 寫入 JSON 檔案
    print('\n寫入 JSON 檔案...')

    posts_file = os.path.join(OUTPUT_DIR, 'posts.json')
    with open(posts_file, 'w', encoding='utf-8') as f:
        json.dump(posts, f, ensure_ascii=False, indent=2)
    print(f'  - {posts_file}')

    daily_file = os.path.join(OUTPUT_DIR, 'daily.json')
    with open(daily_file, 'w', encoding='utf-8') as f:
        json.dump(daily, f, ensure_ascii=False, indent=2)
    print(f'  - {daily_file}')

    stats_file = os.path.join(OUTPUT_DIR, 'stats.json')
    with open(stats_file, 'w', encoding='utf-8') as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    print(f'  - {stats_file}')

    print('\n同步完成!')
    print(f'資料更新時間: {stats["lastUpdated"]}')

if __name__ == '__main__':
    main()
