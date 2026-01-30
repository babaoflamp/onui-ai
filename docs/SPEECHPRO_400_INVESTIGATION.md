# SpeechPro 400 Error Investigation Summary

## Problem Statement
User reported receiving "400 Bad Request" error when attempting to evaluate pronunciation in the SpeechPro practice page. Error message: "Score API 호출 실패: 400 Client Error"

## Root Cause Analysis

The 400 error is returned by the external Score API server (`http://112.220.79.222:33005/speechpro/scorejson`). This could be caused by:

1. **Audio validation failure** - Audio recording too short, too quiet, or invalid format
2. **Metadata format mismatch** - syll_ltrs, syll_phns, or fst fields not in expected format
3. **Score API server issue** - The remote server may have configuration issues or be temporarily unavailable
4. **Payload size limits** - Very long sentences may exceed API limits

## Solutions Implemented

### 1. Enhanced Frontend Logging (speechpro-practice.html)
- Added detailed console logging showing metadata attachment status
- Logs audio blob size, type, and metadata field lengths
- Added automatic validation endpoint call before submitting to Score API
- Provides better visibility into what data is being sent

**Logs added:**
```javascript
[Evaluate] Metadata attached: {
  syll_ltrs_len: ...,
  syll_phns_len: ...,
  fst_len: ...,
  text_len: ...,
  audio_blob_size: ...,
  audio_blob_type: ...
}

[Evaluate] Validation result: { ... }
```

### 2. Backend Validation Endpoint (backend/routes/speechpro.py)
- Created new `/api/speechpro/validate` endpoint
- Validates all data before sending to Score API
- Returns detailed validation results for each field
- Checks WAV header validity for audio
- Accessible from frontend for diagnostic purposes

**Response format:**
```json
{
  "validation": {
    "text": {"value": "...", "length": 13, "valid": true},
    "syll_ltrs": {"length": 47, "valid": true, "has_pipes": true},
    "syll_phns": {"length": 149, "valid": true, "starts_with": "..."},
    "fst": {"length": 28148, "valid": true, "starts_with": "1v2yf..."},
    "audio": {"size": 32000, "valid": true, "is_wav": true}
  },
  "all_valid": true,
  "success": true
}
```

### 3. Improved Backend Logging (backend/services/speechpro_service.py)
- Enhanced audio validation with better messages
- Added audio size adequacy checks (warning if < 1000 bytes)
- Better WAV header detection and logging
- More detailed 4xx error logging with payload previews

**Sample logs:**
```
[Score] Audio size: 6444 bytes, Base64 size: 8592, Text: 서울은...
[Score] ✓ Audio data size adequate: 6444 bytes
[Score] ✓ Valid WAV header detected
[Score] Sending payload with:
  - Text: 서울은...
  - syll_ltrs length: 63
  - syll_phns length: 209
  - fst length: 28148
  - wav_usr length: 8592
[Score] Client error (status=400): 400 Bad Request
```

### 4. Diagnostic Script (scripts/test_speechpro_score_api.py)
- Created comprehensive diagnostic tool
- Tests API connectivity
- Tests with real CSV metadata
- Tests with minimal data
- Provides detailed troubleshooting guidance

**Usage:**
```bash
python scripts/test_speechpro_score_api.py
```

**Output includes:**
- Connectivity test to Score API
- Validation of CSV data
- FST base64 decoding check
- Audio format validation
- Detailed error messages

### 5. Troubleshooting Guide (docs/SPEECHPRO_400_ERROR_GUIDE.md)
- Comprehensive user-facing guide
- Step-by-step diagnostics
- Common issues and solutions
- Browser console navigation
- Server log interpretation
- Validation endpoint examples

## How to Use the Solutions

### For Users Encountering 400 Error:

1. **Check Browser Console:**
   - Press F12 to open DevTools
   - Go to Console tab
   - Look for `[Evaluate] Metadata attached` logs
   - Verify all metadata fields are present and non-empty

2. **Check Audio Quality:**
   - Ensure `audio_blob_size > 5000` bytes
   - Verify microphone is working
   - Speak clearly and loud enough

3. **Try Shorter Sentences:**
   - Use 5-20 character sentences
   - Avoid very complex text
   - Test with simple sentences like "안녕하세요"

4. **Use Validation Endpoint:**
   - Open browser console
   - Run validation before evaluation
   - Check validation results

### For Developers Debugging:

1. **Run Diagnostic Script:**
   ```bash
   python scripts/test_speechpro_score_api.py
   ```

2. **Check Server Logs:**
   - Monitor backend console during evaluation
   - Look for `[Score]` prefixed messages
   - Verify all data is present and valid size

3. **Test Validation Endpoint:**
   ```bash
   curl -X POST http://localhost:9000/api/speechpro/validate \
     -F "text=테스트" \
     -F "audio=@test.wav" \
     -F "syll_ltrs=..." \
     -F "syll_phns=..." \
     -F "fst=..."
   ```

4. **Check Remote API:**
   ```bash
   curl -v http://112.220.79.222:33005/speechpro/scorejson
   ```

## Testing the Fixes

### Test Case 1: Normal Flow
```
1. Select sentence with metadata
2. Verify [Evaluate] Metadata attached log
3. Record audio (> 2 seconds)
4. Click evaluate
5. Check browser console for validation result
6. Check server logs for Score API response
```

### Test Case 2: Missing Metadata
```
1. Manually enter text without CSV metadata
2. Verify validation fails
3. System should call generate-metadata endpoint
4. Verify metadata is populated
5. Continue with evaluation
```

### Test Case 3: Short Audio
```
1. Record very short audio (< 1 second)
2. Browser console should show: audio_blob_size < 5000
3. Server logs should show: WARNING: Audio data small
4. Score API likely to return 400
```

## Known Limitations

1. **Score API is External:** The remote Score API server (`112.220.79.222:33005`) is not under our control. If it's down or misconfigured, we cannot fix it from our side.

2. **Audio Format:** Browser's MediaRecorder may use different codecs (WebM, Opus) depending on browser. Backend handles conversion via ffmpeg, but this depends on having valid ffmpeg installation.

3. **Metadata Dependency:** Without proper metadata (syll_ltrs, syll_phns, fst), the Score API may reject the request. CSV must be properly formatted.

4. **Timeout:** Score API has a 30-second timeout. Very long sentences or network delays may timeout.

## Recommendations

1. **For Production:**
   - Monitor the diagnostic endpoint usage
   - Log all Score API responses (including 400 errors) for analysis
   - Consider local FST generation if CSV is incomplete

2. **For Users:**
   - Always record > 1 second of audio
   - Speak clearly and naturally
   - Use sentences from the preset list for best results
   - Report specific error messages with browser console logs

3. **For Future Enhancement:**
   - Implement retry logic for temporary failures
   - Add audio quality indicators during recording
   - Provide visual feedback on metadata loading
   - Consider caching metadata locally

## Files Modified

1. `templates/speechpro-practice.html` - Added frontend validation and logging
2. `backend/routes/speechpro.py` - Added validation endpoint
3. `backend/services/speechpro_service.py` - Enhanced error logging
4. `scripts/test_speechpro_score_api.py` - New diagnostic script
5. `docs/SPEECHPRO_400_ERROR_GUIDE.md` - New troubleshooting guide

## Conclusion

The 400 error is fundamentally a communication issue between our backend and the external Score API. The solutions implemented provide:

1. **Better visibility** into what data is being sent
2. **Validation tools** to identify problematic data early
3. **Diagnostic capabilities** for troubleshooting
4. **User guidance** for resolving common issues

The error message itself ("문장이 너무 길거나 복잡할 수 있습니다") suggests the Score API is correctly identifying the issue and our frontend is properly communicating it to users.
