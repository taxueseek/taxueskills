#!/usr/bin/env python3
"""tests/test_price_lookup.py — 全网比价查询脚本测试

覆盖：
  - 账号配置：缺省公开演示标识 / SHOPPING_OPENID、SHOPPING_INVITE 注入两条路径
  - search：POST 表单字段（keyword/openid/sourceType/page）与响应解析
    （平台名映射、标题去空白、价格/月销/商品 ID/图片）
  - detail：详情 + 购买链接两步接口，inviteCode/usageScene 等字段落位，
    无链接时的兜底行为
  - CLI：search / detail 子命令参数解析、缺参数错误分支

全程 mock 网络层，离线必过。
"""

from __future__ import annotations

import importlib
import io
import json
import os
import sys
import unittest
import urllib.parse as up
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import MagicMock, patch

SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPT_DIR = SKILL_DIR / "scripts"
for p in (str(SCRIPT_DIR),):
    if p not in sys.path:
        sys.path.insert(0, p)

import price_lookup  # noqa: E402

DEFAULT_OPENID = "564bdce0fa408fc9e1d5d42fd022ef0b"
DEFAULT_INVITE = "6110440"


def _fake_response(payload: dict):
    """构造 mock urlopen 的上下文管理器响应，read() 返回 JSON 字节。"""
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    resp = MagicMock()
    resp.read.return_value = raw
    resp.__enter__.return_value = resp
    return resp


# ── 账号配置：缺省 vs 注入 ──────────────────────────────────────────────

class TestAccountConfig(unittest.TestCase):
    """openid / 邀请码：缺省用公开演示标识，环境变量可覆盖。"""

    def _reload(self):
        return importlib.reload(price_lookup)

    def test_defaults_when_env_unset(self):
        with patch.dict(os.environ, {}, clear=True):
            mod = self._reload()
        self.assertEqual(mod.OPENID, DEFAULT_OPENID)
        self.assertEqual(mod.INVITE_CODE, DEFAULT_INVITE)

    def test_openid_from_env(self):
        with patch.dict(os.environ, {"SHOPPING_OPENID": "openid-test-001"}, clear=True):
            mod = self._reload()
        self.assertEqual(mod.OPENID, "openid-test-001")
        self.assertEqual(mod.INVITE_CODE, DEFAULT_INVITE)

    def test_invite_from_env(self):
        with patch.dict(os.environ, {"SHOPPING_INVITE": "invite-999"}, clear=True):
            mod = self._reload()
        self.assertEqual(mod.INVITE_CODE, "invite-999")
        self.assertEqual(mod.OPENID, DEFAULT_OPENID)


# ── search：请求与解析 ──────────────────────────────────────────────────

class TestSearch(unittest.TestCase):
    @patch.object(price_lookup, "OPENID", "openid-test-001")
    @patch("price_lookup.urllib.request.urlopen")
    def test_form_and_parse(self, mock_urlopen):
        rows = [
            {
                "title": "  iPhone 17 128G  ",
                "shopName": "Apple 旗舰店",
                "originalPrice": "5999",
                "couponPrice": "200",
                "actualPrice": "5799",
                "monthSales": "70000",
                "sourceType": "1",
                "goodsId": "g-1001",
                "picUrl": "https://img.example/1.jpg",
            },
            {
                "title": "iPhone 17 保护壳",
                "shopName": "",
                "originalPrice": "49",
                "couponPrice": "0",
                "actualPrice": "39",
                "monthSales": "1200",
                "sourceType": "2",
                "goodsId": "g-1002",
                "picUrl": "",
            },
        ]
        mock_urlopen.return_value = _fake_response({"data": rows})

        items = price_lookup.search("iPhone 17", source="1", page=2)

        self.assertEqual(len(items), 2)
        first = items[0]
        self.assertEqual(first["title"], "iPhone 17 128G")  # 去空白
        self.assertEqual(first["shop"], "Apple 旗舰店")
        self.assertEqual(first["platform"], "淘宝/天猫")     # sourceType 1 → 淘宝/天猫
        self.assertEqual(first["original_price"], "5999")
        self.assertEqual(first["actual_price"], "5799")
        self.assertEqual(first["coupon_price"], "200")
        self.assertEqual(first["monthly_sales"], "70000")
        self.assertEqual(first["goods_id"], "g-1001")
        self.assertEqual(first["pic_url"], "https://img.example/1.jpg")
        self.assertEqual(items[1]["platform"], "京东")      # sourceType 2 → 京东

        req = mock_urlopen.call_args[0][0]
        self.assertEqual(req.full_url, price_lookup.SEARCH_URL)
        self.assertEqual(req.get_method(), "POST")
        body = up.parse_qs(req.data.decode("utf-8"))
        self.assertEqual(body["keyword"], ["iPhone 17"])
        self.assertEqual(body["openid"], ["openid-test-001"])
        self.assertEqual(body["sourceType"], ["1"])
        self.assertEqual(body["page"], ["2"])
        self.assertEqual(req.get_header("Openid"), "openid-test-001")

    @patch("price_lookup.urllib.request.urlopen")
    def test_empty_data_returns_empty_list(self, mock_urlopen):
        mock_urlopen.return_value = _fake_response({"code": 0, "data": None})
        self.assertEqual(price_lookup.search("不存在的东西"), [])

    @patch("price_lookup.urllib.request.urlopen")
    def test_unknown_source_keeps_raw(self, mock_urlopen):
        mock_urlopen.return_value = _fake_response(
            {"data": [{"title": "x", "sourceType": "9"}]})
        items = price_lookup.search("x")
        self.assertEqual(items[0]["platform"], "平台9")

    @patch.object(price_lookup, "OPENID", "openid-test-001")
    @patch("price_lookup.urllib.request.urlopen")
    def test_default_source_is_all(self, mock_urlopen):
        mock_urlopen.return_value = _fake_response({"data": []})
        price_lookup.search("洗衣机")
        req = mock_urlopen.call_args[0][0]
        body = up.parse_qs(req.data.decode("utf-8"))
        self.assertEqual(body["sourceType"], ["0"])
        self.assertEqual(body["page"], ["1"])


# ── detail：双接口与兜底 ────────────────────────────────────────────────

class TestDetail(unittest.TestCase):
    @patch.object(price_lookup, "OPENID", "openid-test-001")
    @patch.object(price_lookup, "INVITE_CODE", "invite-999")
    @patch("price_lookup.urllib.request.urlopen")
    def test_two_endpoints_and_fields(self, mock_urlopen):
        mock_urlopen.side_effect = [
            _fake_response({"data": {"title": "iPhone 17 256G", "price": "6599"}}),
            _fake_response({"data": {"appUrl": "https://buy.example/1001",
                                     "kl": "复制口令ABC"}}),
        ]

        info = price_lookup.detail("g-1001", source="1")

        self.assertEqual(info["title"], "iPhone 17 256G")
        self.assertEqual(info["buy_link"], "https://buy.example/1001")
        self.assertEqual(info["share_text"], "复制口令ABC")
        self.assertIn("price", info["detail"])
        self.assertEqual(mock_urlopen.call_count, 2)

        first_req, second_req = [c[0][0] for c in mock_urlopen.call_args_list]
        self.assertEqual(first_req.full_url, price_lookup.DETAIL_URL)
        self.assertEqual(second_req.full_url, price_lookup.TARGET_URL)

        detail_body = json.loads(first_req.data.decode("utf-8"))
        self.assertEqual(detail_body["goodsId"], "g-1001")
        self.assertEqual(detail_body["sourceType"], "1")
        self.assertEqual(detail_body["inviteCode"], "invite-999")
        self.assertEqual(detail_body["usageScene"], 5)
        self.assertEqual(detail_body["isShare"], "1")

        target_body = json.loads(second_req.data.decode("utf-8"))
        self.assertEqual(target_body["goodsId"], "g-1001")
        self.assertEqual(second_req.get_header("Openid"), "openid-test-001")

    @patch("price_lookup.urllib.request.urlopen")
    def test_missing_target_link_falls_back_schema(self, mock_urlopen):
        mock_urlopen.side_effect = [
            _fake_response({"data": {"title": "商品X"}}),
            _fake_response({"data": {"schemaUrl": "sx://goods/200"}}),
        ]
        info = price_lookup.detail("g-200", source="3")
        self.assertEqual(info["buy_link"], "sx://goods/200")

    @patch("price_lookup.urllib.request.urlopen")
    def test_no_target_data_returns_none(self, mock_urlopen):
        mock_urlopen.side_effect = [
            _fake_response({"data": {"title": "商品Y"}}),
            _fake_response({"data": {}}),
        ]
        info = price_lookup.detail("g-300", source="3")
        self.assertIsNone(info["buy_link"])
        self.assertIsNone(info["share_text"])

    @patch("price_lookup.urllib.request.urlopen")
    def test_empty_detail_data(self, mock_urlopen):
        mock_urlopen.side_effect = [
            _fake_response({"data": None}),
            _fake_response({"data": {}}),
        ]
        info = price_lookup.detail("g-400", source="3")
        self.assertEqual(info["title"], "")
        self.assertEqual(info["detail"], {})


# ── CLI ─────────────────────────────────────────────────────────────────

class TestCli(unittest.TestCase):
    @patch("price_lookup._print_search")
    @patch("price_lookup.search")
    def test_main_search_args(self, mock_search, mock_print):
        mock_search.return_value = []
        code = price_lookup.main(["search", "洗衣机", "--source", "2", "--page", "3"])
        self.assertEqual(code, 0)
        mock_search.assert_called_once_with("洗衣机", source="2", page=3)
        mock_print.assert_called_once()

    @patch("price_lookup._print_detail")
    @patch("price_lookup.detail")
    def test_main_detail_args(self, mock_detail, mock_print):
        mock_detail.return_value = {"title": "T"}
        code = price_lookup.main(["detail", "--id", "g-1", "--source", "7"])
        self.assertEqual(code, 0)
        mock_detail.assert_called_once_with("g-1", source="7")
        mock_print.assert_called_once()

    def test_main_missing_keyword_returns_1(self):
        with redirect_stdout(io.StringIO()):
            code = price_lookup.main(["search"])
        self.assertEqual(code, 1)

    def test_main_missing_detail_id_returns_1(self):
        with redirect_stdout(io.StringIO()):
            code = price_lookup.main(["detail"])
        self.assertEqual(code, 1)

    def test_main_no_args_prints_doc_returns_1(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = price_lookup.main([])
        self.assertEqual(code, 1)
        self.assertIn("全网比价查询", buf.getvalue())

    @patch("price_lookup.search")
    def test_main_search_defaults(self, mock_search):
        mock_search.return_value = []
        price_lookup.main(["search", "床垫"])
        mock_search.assert_called_once_with("床垫", source="0", page=1)


if __name__ == "__main__":
    unittest.main()
