import asyncio
import os
from loguru import logger
from onvif import ONVIFCamera

# Hardcode the absolute path to the local WSDL directory
# The operator must manually copy the wsdl directory here on the remote deployment.
WSDL_DIR = os.path.join(os.path.dirname(__file__), 'wsdl')

def _sync_scan_nvr(ip, port, user, password):
    """
    Synchronous, blocking SOAP execution. 
    Never call this directly from the Uvicorn event loop.
    """
    if not os.path.exists(WSDL_DIR):
        raise FileNotFoundError(f"WSDL Directory not found at {WSDL_DIR}. You must bundle the ONVIF WSDL files locally.")

    logger.info(f"🔍 Initializing ONVIF connection to {ip}:{port}...")
    try:
        mycam = ONVIFCamera(ip, port, user, password, WSDL_DIR)
        media_service = mycam.create_media_service()
        
        logger.info(f"📡 Requesting Profiles from {ip}...")
        profiles = media_service.GetProfiles()
        
        cameras = []
        for profile in profiles:
            try:
                # Extract RTSP URI for this profile
                req = media_service.create_type('GetStreamUri')
                req.ProfileToken = profile.token
                req.StreamSetup = {'Stream': 'RTP-Unicast', 'Transport': {'Protocol': 'RTSP'}}
                uri = media_service.GetStreamUri(req)
                
                cameras.append({
                    "name": profile.Name,
                    "rtsp_url": uri.Uri,
                    "camera_id": f"cam_{profile.Name.lower().replace(' ', '_')}"
                })
            except Exception as e:
                logger.warning(f"⚠️ Failed to extract stream for Profile {profile.Name}: {e}")
                
        logger.info(f"✅ ONVIF Discovery Complete. Found {len(cameras)} profiles.")
        return cameras
    except Exception as e:
        logger.error(f"❌ ONVIF Connection Failed: {e}")
        raise

async def async_scan_nvr(ip, port, user, password):
    """
    Wraps the heavy synchronous ONVIF SOAP client in a separate thread.
    Returns: list of dicts [{'name': '...', 'rtsp_url': '...'}, ...]
    """
    return await asyncio.to_thread(_sync_scan_nvr, ip, port, user, password)
