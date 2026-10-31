"""告警通道 — 当前为 log stub,后续接 Slack/企微。"""
import logging

logger = logging.getLogger("alerts")


class Notifier:
    """统一告警接口。"""

    async def send(self, channel: str, message: str, severity: str = "info", **metadata):
        log_method = getattr(logger, severity if severity != "critical" else "critical", logger.info)
        log_method(
            f"[alert:{channel}] {message}",
            extra={"channel": channel, "severity": severity, **metadata},
        )

    async def send_bad_case(self, bad_case_id: str, review_id: str, severity: str):
        await self.send(
            channel="bad_case",
            message=f"New bad case detected: {bad_case_id} for review {review_id}",
            severity=severity,
            review_id=review_id,
            bad_case_id=bad_case_id,
        )


notifier = Notifier()