"""웹훅 알림 노드 핸들러 — Slack/Teams/Discord/Generic 페이로드 분기"""
from datetime import datetime, timezone
from typing import Any, Dict, List

import httpx

from ..registry import NodeHandlerRegistry
from ..base import NodeHandler, ExecutionContext


SUPPORTED_PLATFORMS = ("slack", "teams", "discord", "generic")


@NodeHandlerRegistry.register
class WebhookNotifyHandler(NodeHandler):
    node_type = "webhook-notify"
    category = "action"
    display_name = "웹훅 알림"
    description = "Slack/Teams/Discord 등 incoming webhook으로 알림 메시지를 전송합니다"

    async def execute(
        self,
        node: Any,
        input_data: Dict[str, Any],
        ctx: ExecutionContext,
    ) -> Any:
        config = node.config or {}

        webhook_url_raw = config.get('webhookUrl', '')
        webhook_url = ctx.render_template(webhook_url_raw, input_data) if ctx.render_template else webhook_url_raw
        if not webhook_url:
            raise ValueError("webhookUrl이 설정되지 않았습니다")

        platform = (config.get('platform') or 'generic').lower()
        if platform not in SUPPORTED_PLATFORMS:
            raise ValueError(f"지원하지 않는 platform: {platform} (지원: {', '.join(SUPPORTED_PLATFORMS)})")

        message_template = config.get('messageTemplate', '')
        title_template = config.get('titleTemplate', '') or ''
        mention_users: List[str] = config.get('mentionUsers') or []

        message = ctx.render_template(message_template, input_data) if ctx.render_template else message_template
        title = ctx.render_template(title_template, input_data) if ctx.render_template else title_template

        # Slack mention prefix
        if platform == 'slack' and mention_users:
            mentions = ' '.join(
                m if m.startswith('<@') else f"<@{m}>"
                for m in mention_users
                if m
            )
            if mentions:
                message = f"{mentions} {message}".strip()

        # Platform별 페이로드 구성
        if platform == 'slack':
            payload: Dict[str, Any] = {"text": message}
        elif platform == 'teams':
            payload = {"text": message}
            if title:
                payload["title"] = title
        elif platform == 'discord':
            payload = {"content": message}
        else:  # generic
            payload = {
                "message": message,
                "title": title,
                "ts": datetime.now(timezone.utc).isoformat(),
            }

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.post(webhook_url, json=payload)
        except httpx.HTTPError as e:
            raise ValueError(f"웹훅 전송 실패: {e}")

        if response.status_code >= 500:
            raise ValueError(
                f"웹훅 수신 서버 오류: status={response.status_code}, body={response.text[:200]}"
            )

        return {
            "delivered": 200 <= response.status_code < 400,
            "status": response.status_code,
            "platform": platform,
        }
