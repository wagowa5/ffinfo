import requests
import os
import json
from openai import OpenAI

# 各環境変数を定数化
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')
REPOSITORY = os.getenv("REPOSITORY")
PR_NUMBER = int(os.getenv("PR_NUMBER"))
# GitHubのPull Request API URL
PR_API_URL = f'https://api.github.com/repos/{REPOSITORY}/pulls/{PR_NUMBER}'

# PRのdiffを取得する
def get_pr_diff():
    headers = {
        'Authorization': f'token {GITHUB_TOKEN}',
        'Accept': 'application/vnd.github.v3.diff'
    }
    diff_response = requests.get(PR_API_URL, headers=headers)
    return diff_response.text

# Open AI APIでコードレビューを行い結果をjsonで返却する
def get_openai_review(prompt):
    client = OpenAI(api_key=OPENAI_API_KEY)
    # レスポンスをjson、modelにGPT-4 Turboを指定
    chat_completion = client.chat.completions.create(
        model="gpt-4-0125-preview",
        messages=[
            {
                "role": "system",
                "content": "This GPT is configured to analyze differences in GitHub and provide code reviews in Japanese. The goal is to offer concrete suggestions to improve the quality of the code, as well as insights into areas of improvement, with an emphasis on efficiency, maintainability, security, and adherence to styles and standards. Efficiency assesses whether the code uses resources efficiently (from the perspectives of time and memory). Maintainability considers whether the code will be easy for other developers to understand and modify in the future. Security checks if the code avoids potential security risks. Styles and standards examine whether coding standards and style guides are being followed. The review results are provided in JSON format, which contains review comments for each file. The \"files\" key indicates an array of reviewed files, \"fileName\" indicates the file name, and \"reviews\" indicates an array of review comments within that file. Each review comment contains \"lineNumber\" and \"reviewComment\" keys, representing the target line number and the review comment, respectively. The tone of the conversation should be strictly professional."},
            {
                "role": "user",
                "content": prompt,
            }
        ],
        response_format={"type":"json_object"}, 
    )
    review_result = chat_completion.choices[0].message.content
    return review_result

# コードレビューを依頼するプロンプトを作成
def create_prompt(code_diff):
    prompt = (f'Review the following code:\n\n{code_diff}\n\n'
              '- Be sure to comment on areas for improvement.\n'
              '- Please make review comments in Japanese.\n'
              '- Ignore the use of "self." when using variables and functions.\n'
              '- The following json format should be followed.\n'
              '{"files":[{"fileName":"<file_name>","reviews": [{"lineNumber":<line_number>,"reviewComment":"<review comment>"}]}]}\n'
              '- If there is no review comment, please answer {"files":[]}\n')
    prompt += create_ignore_pr_reviews_prompt()
    return prompt

# 既にコメントされている場合は同じコメントをしないように依頼するプロンプトを作成
def create_ignore_pr_reviews_prompt():
    url = f'{PR_API_URL}/comments'
    headers = {'Authorization': f'token {GITHUB_TOKEN}'}
    response = requests.get(url, headers=headers)
    comments = response.json()
    if len(comments) == 0:
        return ""
    ignore_prompt = '- However, please ensure the content does not duplicate the following existing comments:\n'
    for comment in comments:
        body = comment['body']
        path = comment.get('path')
        line = comment.get('line') or comment.get('original_line')
        ignore_prompt += f'  - file "{path}", line {line}: {body}\n'
    return ignore_prompt

# レビューコメントを投稿する
def post_review_comments(review_files):
    url = f'{PR_API_URL}/commits'
    headers = {
        'Authorization': f'token {GITHUB_TOKEN}',
        'Accept': 'application/vnd.github.v3+json'
    }
    pr_commits_response = requests.get(url, headers=headers)
    pr_commits = pr_commits_response.json()
    last_commit = pr_commits[-1]['sha']
    for file in review_files["files"]:
        for review in file["reviews"]:
            comment_url = f'{PR_API_URL}/comments'
            comment_data = {
                'body': review["reviewComment"],
                'commit_id': last_commit,
                'path': file["fileName"],
                'position': review["lineNumber"]
            }
            requests.post(comment_url, headers=headers, data=json.dumps(comment_data))

code_diff = get_pr_diff()
prompt = create_prompt(code_diff)
review_json = get_openai_review(prompt)
post_review_comments(json.loads(review_json))
