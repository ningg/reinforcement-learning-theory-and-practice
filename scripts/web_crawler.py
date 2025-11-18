import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import os
import pypandoc
import time

def get_headers(url):
    """
    根据 URL 返回合适的请求头，针对不同网站优化
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'Accept-Language': 'zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Sec-Fetch-User': '?1',
        'Cache-Control': 'max-age=0',
    }
    
    # 针对知乎添加 Referer
    if 'zhihu.com' in url:
        headers['Referer'] = 'https://www.zhihu.com/'
        headers['Origin'] = 'https://www.zhihu.com'
    
    return headers

def clean_url(url):
    """
    截取 # 之前的部分，去除 fragment
    """
    return url.split('#')[0]

def save_image(img_url, save_dir="docs/images", session=None):
    try:
        os.makedirs(save_dir, exist_ok=True)
        filename = urlparse(img_url).path.split('/')[-1]
        # 处理没有扩展名的文件名
        if not filename or '.' not in filename:
            filename = f"image_{hash(img_url) % 10000}.jpg"
        save_path = os.path.join(save_dir, filename)
        if not os.path.exists(save_path):
            headers = get_headers(img_url)
            if session:
                resp = session.get(img_url, headers=headers, timeout=10)
            else:
                resp = requests.get(img_url, headers=headers, timeout=10)
            resp.raise_for_status()
            with open(save_path, "wb") as f:
                f.write(resp.content)
            print(f"Image saved: {save_path}")
        return save_path
    except Exception as e:
        print(f"Error saving image {img_url}: {e}")
        return None

def html_to_markdown(html, page_dir="pages", img_dir="images"):
    """
    Convert HTML to Markdown using pypandoc.
    """
    # pypandoc will keep local image and code block formatting intact
    md = pypandoc.convert_text(html, 'md', format='html')
    return md

def fetch_and_save(url, save_dir="docs", img_dir="docs/images", max_retries=3, cookies=None):
    """
    获取并保存网页内容
    
    Args:
        url: 要抓取的 URL
        save_dir: 保存目录
        img_dir: 图片保存目录
        max_retries: 最大重试次数
        cookies: 可选的 Cookie 字典或字符串，用于需要登录的网站
                例如: {'key': 'value'} 或 "key1=value1; key2=value2"
    """
    print(f"Fetching: {url}")
    
    # 使用 Session 保持连接，提高成功率
    session = requests.Session()
    
    # 处理 Cookie
    if cookies:
        if isinstance(cookies, str):
            # 将字符串格式的 Cookie 转换为字典
            cookie_dict = {}
            for item in cookies.split(';'):
                if '=' in item:
                    key, value = item.strip().split('=', 1)
                    cookie_dict[key] = value
            session.cookies.update(cookie_dict)
        elif isinstance(cookies, dict):
            session.cookies.update(cookies)
    
    for attempt in range(max_retries):
        try:
            headers = get_headers(url)
            response = session.get(url, headers=headers, timeout=15, allow_redirects=True)
            
            # 检查响应状态
            if response.status_code == 403:
                print(f"403 Forbidden - 尝试 {attempt + 1}/{max_retries}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)  # 指数退避
                    continue
                else:
                    print("提示: 如果持续遇到 403 错误，可能需要:")
                    print("  1. 使用浏览器访问该页面，复制 Cookie 到脚本")
                    print("  2. 使用 selenium 等工具模拟浏览器")
                    raise requests.exceptions.HTTPError(f"403 Forbidden after {max_retries} attempts")
            
            response.raise_for_status()
            
            # 检测编码
            if response.encoding is None or response.encoding == 'ISO-8859-1':
                response.encoding = response.apparent_encoding or 'utf-8'
            
            html = response.text
            
            # 保存页面
            parsed = urlparse(url)
            path = parsed.path.replace('/', '_').strip('_') or 'index'
            # 清理文件名中的特殊字符
            path = ''.join(c if c.isalnum() or c in ('_', '-') else '_' for c in path)
            html_filename = f"{save_dir}/{path}.html"
            md_filename = f"{save_dir}/{path}.md"
            os.makedirs(save_dir, exist_ok=True)
            os.makedirs(img_dir, exist_ok=True)
            
            # 解析页面内容
            soup = BeautifulSoup(html, "html.parser")
            
            # 下载并替换图片链接
            img_count = 0
            for img in soup.find_all("img", src=True):
                img_url = urljoin(url, img["src"])
                local_img_path = save_image(img_url, save_dir=img_dir, session=session)
                if local_img_path:
                    img['src'] = os.path.relpath(local_img_path, start=save_dir)
                    img_count += 1
                time.sleep(0.5)  # 避免请求过快
            
            print(f"Downloaded {img_count} images")
            
            # 保存修改后的 HTML
            with open(html_filename, 'w', encoding='utf-8') as f:
                f.write(str(soup))
            print(f"Page saved: {html_filename}")
            
            # 转换并保存为 Markdown
            try:
                md_content = html_to_markdown(str(soup), page_dir=save_dir, img_dir=img_dir)
                with open(md_filename, 'w', encoding='utf-8') as f:
                    f.write(md_content)
                print(f"Markdown saved: {md_filename}")
            except Exception as e:
                print(f"Warning: Failed to convert to Markdown: {e}")
                print("HTML file saved successfully")
            
            return  # 成功则退出
            
        except requests.exceptions.RequestException as e:
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt
                print(f"Error (attempt {attempt + 1}/{max_retries}): {e}")
                print(f"Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
            else:
                print(f"Error fetching {url} after {max_retries} attempts: {e}")
                raise
        except Exception as e:
            print(f"Unexpected error: {e}")
            raise

def main(start_url, cookies=None):
    """
    主函数
    
    Args:
        start_url: 要抓取的起始 URL
        cookies: 可选的 Cookie，用于需要登录的网站
                获取方法: 在浏览器中打开开发者工具 -> Network -> 找到请求 -> Headers -> 复制 Cookie 值
    """
    url = clean_url(start_url)
    fetch_and_save(url, cookies=cookies)
    print("Done.")

if __name__ == "__main__":
    # 替换成你要抓取的起始页面
    cookies = "__snaker__id=p9mVmUmmKjmgMDlK; SESSIONID=comx5k62FnK6RULXBdcSKcR7DLTPDOszF5JCfchBlPh; JOID=U18XBE2UASTrJY13VUWh9Ccai7xMsScCyQGoUXOwJALNB6lSc3tePIQkjndRyVGnWCLkdXYFTuWkF7WJh0dnGq0=; osd=VVEWBkiSDyXpIIt5VEek8ikbiblKvyYAzAemUHG1IgzMBaxUfXpcOYIqj3VUz1-mWifie3cHS-OqFreMgUlmGKg=; _xsrf=1OJEu7fWEWq2OhhC1p9vI7ykGDtHkGu4; _zap=762b55fe-3fc8-4812-82ec-a4433e72e3f4; d_c0=04TTmy8AyhqPTmKgvIsDSoovSIb2ZMOeIm4=|1753012638; Hm_lvt_bff3d83079cef1ed8fc5e3f4579ec3b3=1756026543,1757389116; __zse_ck=004_jPE5OinrYOwgWI3ZHnHVTPGn6WhJT9omdN6swAqSQhl3pKLtCfAalrck419sKWT0IYtA3UXXxT7fWrsNQUvV9o0EUrLs0jnqQ7GR=DHkXWs6w1FJqQ2WeVIWvF7yAOfF-X3wK03h5j6xAPcAIZnJ6pp8oMmLyXsXT5AqCgBaLtR4t7pWbdVwV/WRvBNt22hkXqJQ6cEXmtRKE3cW/78rzI/pKvZSrS3NUv35nN7bOAswaeFOU8tBo5Nun23bjdGi7; z_c0=2|1:0|10:1763303012|4:z_c0|92:Mi4xaEVOSUFBQUFBQURUaE5PYkx3REtHaVlBQUFCZ0FsVk5aQ3dIYWdERTE2ZHV0WlN2aWRMaGs5ZUJuX3FNck0xcW9R|eea619d0e36fcca19fdfe47307950cc74474d0d5ce064ce4616ac3b135ca9ff0; Hm_lvt_98beee57fd2ef70ccdd5ca52b9740c49=1760940614,1762432479,1763300554,1763467240; Hm_lpvt_98beee57fd2ef70ccdd5ca52b9740c49=1763467240; HMACCOUNT=00D4A1099156DAE5"
    main("https://zhuanlan.zhihu.com/p/693582342", cookies)