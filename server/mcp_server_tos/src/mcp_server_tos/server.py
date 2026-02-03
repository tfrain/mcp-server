import base64
import json
import logging
import os
from typing import Optional

from mcp.server.session import ServerSession
from mcp.server.fastmcp import Context, FastMCP
from starlette.requests import Request

from mcp_server_tos.config import load_config, TosConfig, TOS_CONFIG, LOCAL_DEPLOY_MODE
from mcp_server_tos.credential import Credential
from mcp_server_tos.resources.bucket import BucketResource
from mcp_server_tos.resources.object import ObjectResource

logger = logging.getLogger(__name__)

# Initialize FastMCP server
mcp = FastMCP("TOS MCP Server", host=os.getenv("MCP_SERVER_HOST", "127.0.0.1"), port=int(os.getenv("PORT", "8000")))


def get_credential_from_request():
    ctx: Context[ServerSession, object] = mcp.get_context()
    raw_request: Request | None = ctx.request_context.request

    auth = None
    if raw_request:
        # 从 header 的 authorization 字段读取 base64 编码后的 sts json
        auth = raw_request.headers.get("authorization", None)
    if auth is None:
        # 如果 header 中没有认证信息，可能是 stdio 模式，尝试从环境变量获取
        auth = os.getenv("authorization", None)
    if auth is None:
        # 获取认证信息失败
        raise ValueError("Missing authorization info.")

    if ' ' in auth:
        _, base64_data = auth.split(' ', 1)
    else:
        base64_data = auth

    try:
        # 解码 Base64
        decoded_str = base64.b64decode(base64_data).decode('utf-8')
        data = json.loads(decoded_str)
        # 获取字段
        current_time = data.get('CurrentTime')
        expired_time = data.get('ExpiredTime')
        ak = data.get('AccessKeyId')
        sk = data.get('SecretAccessKey')
        session_token = data.get('SessionToken')
        if not ak or not sk or not session_token:
            raise ValueError("Invalid credentials ak, sk, session_token is null")

        return Credential(ak, sk, session_token, expired_time)
    except Exception as e:
        logger.error(f"Error get credentials: {str(e)}")
        raise


def get_tos_config() -> TosConfig:
    if TOS_CONFIG.deploy_mode == LOCAL_DEPLOY_MODE:
        return TOS_CONFIG
    else:
        credential = get_credential_from_request()
        return TosConfig(
            access_key=credential.access_key,
            secret_key=credential.secret_key,
            security_token=credential.security_token,
            region=TOS_CONFIG.region,
            endpoint=TOS_CONFIG.endpoint,
            deploy_mode=TOS_CONFIG.deploy_mode,
            max_object_size=TOS_CONFIG.max_object_size,
            buckets=[]
        )


@mcp.tool()
async def list_buckets():
    """
    List all buckets in TOS.
    Returns:
        A list of buckets.
    """
    try:
        config = get_tos_config()
        tos_resource = BucketResource(config)
        buckets = await tos_resource.list_buckets()
        return buckets
    except Exception:
        raise


@mcp.tool()
async def list_objects(bucket: str, prefix: Optional[str] = None, start_after: Optional[str] = None,
                       continuation_token: Optional[str] = None):
    """
    List all objects in a bucket.
    Args:
        bucket: The name of the bucket.
        prefix: The prefix to filter objects.
        start_after: The start after key to filter objects.
        continuation_token: The continuation token to filter objects.
    Returns:
        A list of objects.
    """
    try:
        config = get_tos_config()
        tos_resource = BucketResource(config)
        objects = await tos_resource.list_objects(bucket, prefix, start_after, continuation_token)
        return objects
    except Exception:
        raise


@mcp.tool()
async def get_object(bucket: str, key: str):
    """
    Retrieves an object from VolcEngine TOS. In the GetObject request, specify the full key name for the object.
    Args:
        bucket: The name of the bucket.
        key: The key of the object.
    Returns:
        If the object content is text format, return the content as string.
        If the object content is binary format, return the content as base64 encoded string.
    """
    try:
        config = get_tos_config()
        tos_resource = ObjectResource(config)
        content = await tos_resource.get_object(bucket, key)
        return content
    except Exception:
        raise

@mcp.tool()
async def video_info(bucket_name: str, key: str):
    """
    Retrieves video file information from VolcEngine TOS by calling the video/info API.
    In the request, specify the bucket name and the full object key for the video.
    Args:
        bucket_name: The name of the bucket.
        key: The key of the object (video file).
    Returns:
        return the video file information in json format as string.
    """
    try:
        config = get_tos_config()
        tos_resource = ObjectResource(config)
        content = await tos_resource.video_info(bucket_name, key)
        return content
    except Exception:
        raise

@mcp.tool()
async def video_snapshot(bucket_name: str, key: str, time: Optional[int] = None,
                         width: Optional[int] = None, height: Optional[int] = None, mode: Optional[str] = None,
                         output_format: Optional[str] = None, auto_rotate: Optional[str] = None,
                         saveas_object: Optional[str] = None, saveas_bucket: Optional[str] = None):
    """
    Retrieves a video snapshot from VolcEngine TOS by calling the video/snapshot API.
    In the request, specify the bucket name, the full object key of the video, and the snapshot parameters.
    Args:
        bucket_name: The name of the bucket.
        key: The key of the object (video file).
        time: The timestamp to capture the snapshot, in milliseconds (ms).
        width: The snapshot width in pixels (px). If set to 0, it is calculated automatically based on the original aspect ratio.
        height: The snapshot height in pixels (px). If set to 0, it is calculated automatically based on the original aspect ratio.
        mode: The snapshot mode. If not specified, the default mode captures the frame precisely at the given timestamp.
              If set to "fast", it captures the nearest keyframe before the specified timestamp.
        output_format: The output image format. Supported values:
            - jpg: JPEG format (default).
            - png: PNG format.
        auto_rotate: Whether to rotate automatically. Supported values:
            - auto: Automatically rotates the snapshot based on video metadata after it is generated.
            - w: Forces rotation to a landscape orientation (width > height) based on video metadata after it is generated.
            - h: Forces rotation to a portrait orientation (height > width) based on video metadata after it is generated.
        saveas_object: The object name to save the snapshot as. If not specified, it won’t be saved (no persistence); return the captured frame image.
        saveas_bucket: The bucket name where the snapshot should be saved. If not specified, the current bucket will be used.
    Returns:
        If saveas is specified, return the saveas object information in json format; otherwise, return the snapshot image (JPG or PNG) as a base64-encoded string.
    """
    try:
        config = get_tos_config()
        tos_resource = ObjectResource(config)
        content = await tos_resource.video_snapshot(bucket_name, key, time, width, height, mode, output_format,
                                                    auto_rotate, saveas_object, saveas_bucket)
        return content
    except Exception:
        raise