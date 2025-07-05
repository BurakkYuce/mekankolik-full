# app/security/file_upload.py
import magic
import uuid
import hashlib
from pathlib import Path
from PIL import Image
from typing import Optional, Tuple
from fastapi import HTTPException, UploadFile
from datetime import datetime
import os
import logging
from app.config import settings

logger = logging.getLogger(__name__)
security_logger = logging.getLogger('security')

class SecureFileUpload:
    """Secure file upload handler with comprehensive validation"""
    
    # File type configurations
    ALLOWED_IMAGE_TYPES = {
        'image/jpeg': ['.jpg', '.jpeg'],
        'image/png': ['.png'],
        'image/webp': ['.webp'],
        'image/gif': ['.gif']
    }
    
    # Magic numbers for file type validation
    FILE_SIGNATURES = {
        b'\xFF\xD8\xFF': 'image/jpeg',
        b'\x89\x50\x4E\x47\x0D\x0A\x1A\x0A': 'image/png',
        b'\x47\x49\x46\x38': 'image/gif',
        b'RIFF': 'image/webp'
    }
    
    MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB
    MAX_IMAGE_DIMENSION = 2048
    ALLOWED_CHARS = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_'
    
    @staticmethod
    def validate_file_signature(file_content: bytes) -> Optional[str]:
        """Validate file type using magic numbers"""
        for signature, file_type in SecureFileUpload.FILE_SIGNATURES.items():
            if file_content.startswith(signature):
                return file_type
        
        # WebP special case
        if file_content[8:12] == b'WEBP':
            return 'image/webp'
        
        return None
    
    @staticmethod
    def sanitize_filename(filename: str) -> str:
        """Sanitize filename to prevent directory traversal"""
        # Remove path components
        filename = os.path.basename(filename)
        
        # Remove special characters
        name, ext = os.path.splitext(filename)
        name = ''.join(c for c in name if c in SecureFileUpload.ALLOWED_CHARS)
        
        if not name:
            name = 'file'
        
        return name[:50]  # Limit length
    
    @staticmethod
    def generate_secure_path(user_id: int, filename: str, base_dir: str) -> Tuple[Path, str]:
        """Generate secure file path with user isolation"""
        # Create date-based subdirectories
        date_path = datetime.now().strftime("%Y/%m/%d")
        
        # Generate unique filename
        file_hash = hashlib.sha256(f"{user_id}{datetime.now().timestamp()}".encode()).hexdigest()[:16]
        ext = Path(filename).suffix.lower()
        secure_filename = f"{file_hash}{ext}"
        
        # Full path with user isolation
        full_path = Path(base_dir) / str(user_id) / date_path
        full_path.mkdir(parents=True, exist_ok=True)
        
        return full_path / secure_filename, secure_filename
    
    @staticmethod
    async def validate_and_process_image(
        file: UploadFile,
        user_id: int,
        upload_dir: str,
        allowed_types: Optional[dict] = None
    ) -> dict:
        """Comprehensive image validation and processing"""
        
        if allowed_types is None:
            allowed_types = SecureFileUpload.ALLOWED_IMAGE_TYPES
        
        try:
            # 1. Check file size
            file.file.seek(0, 2)
            file_size = file.file.tell()
            file.file.seek(0)
            
            if file_size == 0:
                raise HTTPException(status_code=400, detail="Empty file")
            
            if file_size > SecureFileUpload.MAX_FILE_SIZE:
                raise HTTPException(
                    status_code=400, 
                    detail=f"File too large. Maximum size: {SecureFileUpload.MAX_FILE_SIZE // 1024 // 1024}MB"
                )
            
            # 2. Read file content
            file_content = await file.read()
            file.file.seek(0)
            
            # 3. Validate file signature (magic numbers)
            detected_type = SecureFileUpload.validate_file_signature(file_content)
            if not detected_type or detected_type not in allowed_types:
                raise HTTPException(status_code=400, detail="Invalid file type")
            
            # 4. Validate with python-magic
            mime_type = magic.from_buffer(file_content, mime=True)
            if mime_type not in allowed_types:
                raise HTTPException(status_code=400, detail=f"File type {mime_type} not allowed")
            
            # 5. Validate file extension
            file_ext = Path(file.filename).suffix.lower()
            if file_ext not in allowed_types[mime_type]:
                raise HTTPException(status_code=400, detail="File extension doesn't match content")
            
            # 6. Generate secure path
            file_path, secure_filename = SecureFileUpload.generate_secure_path(
                user_id, file.filename, upload_dir
            )
            
            # 7. Process with PIL (removes EXIF and validates image)
            temp_path = file_path.with_suffix('.tmp')
            
            # Save temporary file
            with open(temp_path, 'wb') as f:
                f.write(file_content)
            
            try:
                with Image.open(temp_path) as img:
                    # Check image dimensions
                    if img.width > SecureFileUpload.MAX_IMAGE_DIMENSION or \
                       img.height > SecureFileUpload.MAX_IMAGE_DIMENSION:
                        # Resize maintaining aspect ratio
                        img.thumbnail(
                            (SecureFileUpload.MAX_IMAGE_DIMENSION, SecureFileUpload.MAX_IMAGE_DIMENSION),
                            Image.Resampling.LANCZOS
                        )
                    
                    # Remove EXIF data by converting to RGB
                    if img.mode != 'RGB':
                        img = img.convert('RGB')
                    
                    # Create a new image without metadata
                    clean_img = Image.new(img.mode, img.size)
                    clean_img.putdata(list(img.getdata()))
                    
                    # Save with optimization
                    clean_img.save(file_path, 'JPEG', quality=85, optimize=True)
                    
                    # Get final file info
                    final_size = os.path.getsize(file_path)
                    dimensions = f"{clean_img.width}x{clean_img.height}"
                
            except Exception as e:
                logger.error(f"PIL processing failed: {str(e)}")
                raise HTTPException(status_code=400, detail="Invalid image file")
            finally:
                # Clean up temp file
                if temp_path.exists():
                    temp_path.unlink()
            
            # 8. Calculate file hash for integrity
            with open(file_path, 'rb') as f:
                file_hash = hashlib.sha256(f.read()).hexdigest()
            
            return {
                "filename": secure_filename,
                "path": str(file_path),
                "size": final_size,
                "mime_type": mime_type,
                "dimensions": dimensions,
                "hash": file_hash,
                "upload_time": datetime.now().isoformat()
            }
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"File upload error: {str(e)}")
            # Clean up any created files
            if 'file_path' in locals() and file_path.exists():
                file_path.unlink()
            raise HTTPException(status_code=500, detail="File upload failed")

# Virus scanning integration (optional)
class VirusScanner:
    """Integrate with ClamAV or similar"""
    
    @staticmethod
    def scan_file(file_path: Path) -> bool:
        """Scan file for viruses - implement based on your AV solution"""
        # Example with pyclamd
        try:
            import pyclamd
            cd = pyclamd.ClamdUnixSocket()
            
            with open(file_path, 'rb') as f:
                result = cd.scan_stream(f.read())
            
            return result is None  # None means clean
        except:
            # If AV not available, log warning
            logger.warning("Virus scanner not available")
            return True  # Allow if scanner not available

# Helper function for upload rate limiting
async def get_user_upload_count(user_id: int, window_minutes: int = 60) -> int:
    """Get user upload count in the last window_minutes"""
    # This is a placeholder - implement with Redis or database
    # For now, return 0 to allow uploads
    return 0

# ===== ÖRNEK KULLANIM (Router'larınızda kullanın) =====
# from app.security.file_upload import SecureFileUpload
# 
# @router.post("/secure-upload")
# async def secure_upload_endpoint(
#     file: UploadFile = File(...),
#     db: Session = Depends(get_db),
#     current_user: models.User = Depends(get_current_user)
# ):
#     result = await SecureFileUpload.validate_and_process_image(
#         file=file,
#         user_id=current_user.id,
#         upload_dir=settings.upload_dir
#     )
#     return {"status": "success", "filename": result["filename"]}