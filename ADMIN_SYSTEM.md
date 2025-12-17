# Admin Management System

## Overview
Complete role-based admin system with authentication, user management, log monitoring, and API testing capabilities.

## Default Admin Account
- **Email:** `admin@urimalzen.com`
- **Password:** `admin123!@#`
- **Access URL:** `/admin/login`

Environment variables (optional override):
- `ADMIN_EMAIL`
- `ADMIN_PASSWORD`

**Note:** Default account is automatically created on first startup if no admin exists.

---

## Architecture

### Authentication Flow
1. Admin enters credentials at `/admin/login`
2. Calls `/api/login` endpoint with email/password
3. Server validates and returns JWT-like token with `is_admin=true` flag
4. Token stored in `localStorage` as `auth_token`
5. Admin flag stored in `localStorage` as `is_admin`
6. All subsequent requests include `Authorization: Bearer <token>` header

### Token Format
```
user_id|email|timestamp|random_value|is_admin
Example: 1|admin@urimalzen.com|1704067200|abc123def456|true
```

### Authorization
- **Client-side:** JavaScript checks `localStorage.is_admin` before rendering admin UI
- **Server-side:** `_require_admin(request)` decorator validates token and enforces admin status
  - Raises `HTTPException(403)` if token is invalid or user is not admin
  - All protected endpoints return 403 Forbidden to non-admins

---

## Pages & Features

### 1. Admin Login (`/admin/login`)
**Route:** `GET /admin/login`
**Purpose:** Dedicated admin authentication portal

**Features:**
- Email/password form
- Validates `is_admin` flag in response (rejects if false)
- Redirects to `/admin/dashboard` on success
- Clears localStorage on logout

---

### 2. Admin Dashboard (`/admin/dashboard`)
**Route:** `GET /admin/dashboard` (requires admin)
**Purpose:** Home page with KPI cards and navigation menu

**Features:**
- 5 action cards with quick links:
  - 👥 Users: User management
  - 📋 Logs: Activity monitoring
  - 🔧 API Test: Request/response tester
  - ⚙️ Settings: Configuration view
  - 📊 Dashboard: Return to home
- KPI section:
  - Total users count
  - Admin users count
  - Recent signups (last 5 users with timestamp)

**API Dependency:** `/api/admin/summary`

---

### 3. User Management (`/admin/users`)
**Route:** `GET /admin/users` (requires admin)
**Purpose:** View and manage all user accounts

**Features:**
- Search users by email
- Filter by role (Admin / User)
- Paginated table (50 users per page)
- Inline actions:
  - **Toggle Admin:** Make user an admin or revoke admin privileges
  - **Reset Password:** Send user a new temporary password
  - Role badges (Admin / User)

**API Dependencies:**
- `GET /api/admin/users?skip=0&limit=50` - List users
- `POST /api/admin/users/{user_id}/toggle-admin` - Change admin status
- `POST /api/admin/users/{user_id}/reset-password` - Reset password
- `GET /api/admin/users/{user_id}` - User detail (optional)

**Request Body (toggle-admin):**
```json
{
  "is_admin": true  // or false to revoke
}
```

**Request Body (reset-password):**
```json
{
  "new_password": "NewPassword123!@#"
}
```

---

### 4. Log Viewer (`/admin/logs`)
**Route:** `GET /admin/logs` (requires admin)
**Purpose:** Monitor application activity and errors

**Features:**
- Filter by log level (INFO / WARNING / ERROR)
- Search logs by keyword (case-insensitive)
- Display last 100 log lines (configurable)
- Color-coded rows:
  - 🔴 ERROR: Red background
  - 🟡 WARNING: Yellow background
  - 🔵 INFO: Blue background
- Shows timestamp, level, and message

**API Dependency:**
- `GET /api/admin/logs-tail?lines=100&level=ERROR&search=text`

**Query Parameters:**
- `lines` (int): Number of log lines to retrieve (default: 100)
- `level` (string): Filter by level - "INFO", "WARNING", "ERROR" (optional)
- `search` (string): Search term in log message (optional)

---

### 5. API Test Tool (`/admin/api-test`)
**Route:** `GET /admin/api-test` (requires admin)
**Purpose:** Test any API endpoint with custom requests

**Features:**
- Method selector (GET / POST / PUT / DELETE / PATCH)
- URL input (relative paths: `/api/...`)
- Custom headers (multiline editor)
- Request body input (JSON)
- Auto-token option: Automatically adds `Authorization: Bearer <token>` header
- Preset buttons:
  - `/api/admin/summary` - Get dashboard stats
  - `/api/user/profile` - Get current user profile
  - `/api/admin/users` - List all users
- Request history: Last 20 requests saved in localStorage
- Response metrics:
  - Status code (green if <300, red if ≥300)
  - Response time in milliseconds
  - Response size in bytes

**Example Request:**
```
Method: GET
URL: /api/admin/users?skip=0&limit=10
Headers: (auto-token enabled)
Body: (empty for GET)
```

---

### 6. Settings View (`/admin/settings`)
**Route:** `GET /admin/settings` (requires admin)
**Purpose:** Display current server configuration

**Configuration Displayed:**
- **AI Model Backend:** `MODEL_BACKEND` (ollama / gemini)
- **Ollama Model:** `OLLAMA_MODEL` (e.g., exaone)
- **Ollama URL:** `OLLAMA_URL` (e.g., http://localhost:11434)
- **TTS Service:** `MZTTS_API_URL` (Korean TTS endpoint)
- **Romanization Mode:** `ROMANIZE_MODE` (force / prefer)

**Status:** Settings are read-only (sourced from environment variables)

To update settings, restart the server with new environment variables:
```bash
export MODEL_BACKEND=ollama
export OLLAMA_MODEL=exaone
export OLLAMA_URL=http://localhost:11434
python3 main.py
```

---

## API Endpoints

### Admin Summary
**Endpoint:** `GET /api/admin/summary`
**Auth:** Admin required
**Response:**
```json
{
  "total_users": 42,
  "admin_users": 2,
  "recent_signups": [
    {
      "email": "user1@example.com",
      "nickname": "User1",
      "created_at": "2024-01-15 10:30:45"
    }
  ]
}
```

---

### List Users
**Endpoint:** `GET /api/admin/users?skip=0&limit=50`
**Auth:** Admin required
**Response:**
```json
{
  "users": [
    {
      "id": 1,
      "email": "user@example.com",
      "nickname": "UserNickname",
      "is_admin": false,
      "created_at": "2024-01-10 14:20:30"
    }
  ],
  "total": 42
}
```

---

### Get User Detail
**Endpoint:** `GET /api/admin/users/{user_id}`
**Auth:** Admin required
**Response:**
```json
{
  "id": 1,
  "email": "user@example.com",
  "nickname": "UserNickname",
  "is_admin": false,
  "created_at": "2024-01-10 14:20:30"
}
```

---

### Toggle User Admin Status
**Endpoint:** `POST /api/admin/users/{user_id}/toggle-admin`
**Auth:** Admin required
**Request:**
```json
{
  "is_admin": true
}
```
**Response:**
```json
{
  "success": true,
  "message": "관리자 권한이 설정되었습니다."
}
```
**Note:** Admins cannot revoke their own admin privileges

---

### Reset User Password
**Endpoint:** `POST /api/admin/users/{user_id}/reset-password`
**Auth:** Admin required
**Request:**
```json
{
  "new_password": "NewPassword123!@#"
}
```
**Response:**
```json
{
  "success": true,
  "message": "사용자 비밀번호가 변경되었습니다."
}
```

---

### Retrieve Logs
**Endpoint:** `GET /api/admin/logs-tail?lines=100&level=ERROR&search=pattern`
**Auth:** Admin required
**Query Parameters:**
- `lines` (int): Number of lines to retrieve (default: 100)
- `level` (string): Filter by "INFO", "WARNING", "ERROR" (optional)
- `search` (string): Search term (case-insensitive, optional)

**Response:**
```json
{
  "logs": [
    "[2024-01-15 14:30:45] ERROR - Something went wrong: Connection timeout",
    "[2024-01-15 14:30:40] INFO - User logged in: user@example.com",
    "[ADMIN_ACTION] 2024-01-15 14:30:35 - Admin reset password for user ID 5"
  ],
  "total": 3
}
```

---

### Get Settings
**Endpoint:** `GET /api/admin/settings`
**Auth:** Admin required
**Response:**
```json
{
  "settings": {
    "model_backend": "ollama",
    "ollama_url": "http://localhost:11434",
    "ollama_model": "exaone",
    "mztts_url": "http://112.220.79.218:56014",
    "romanize_mode": "force"
  }
}
```

---

## Activity Logging

All admin actions are logged with `[ADMIN_ACTION]` prefix:

**Examples:**
```
[ADMIN_ACTION] 2024-01-15 14:35:20 - Admin (admin@urimalzen.com) made user ID 5 an admin
[ADMIN_ACTION] 2024-01-15 14:35:15 - Admin (admin@urimalzen.com) reset password for user ID 5
[ADMIN_ACTION] 2024-01-15 14:35:10 - Admin accessed /api/admin/summary
```

---

## Security Features

1. **Token-Based Authentication:**
   - Tokens include admin flag and are validated on each request
   - Tokens stored in localStorage (vulnerable to XSS, mitigate with CSP headers)

2. **Role-Based Access Control:**
   - `_require_admin()` enforces admin status on protected routes
   - Returns 403 Forbidden for non-admins
   - Server-side validation on admin pages prevents direct URL access

3. **Admin Self-Protection:**
   - Admins cannot revoke their own admin status
   - Prevents accidental lockout of all admins

4. **Activity Logging:**
   - All admin actions logged with timestamp and actor info
   - Useful for audit trails and troubleshooting

---

## Troubleshooting

### Can't login to admin account
1. Verify default credentials:
   - Email: `admin@urimalzen.com`
   - Password: `admin123!@#`
2. Check environment variables if overridden:
   ```bash
   echo $ADMIN_EMAIL
   echo $ADMIN_PASSWORD
   ```
3. Verify admin account exists in database:
   ```bash
   sqlite3 data/users.db "SELECT id, email, is_admin FROM users WHERE is_admin=1;"
   ```

### Admin links not showing in navigation
1. Check localStorage:
   ```javascript
   // In browser console
   localStorage.getItem('is_admin')  // Should be "true"
   ```
2. Verify token is valid:
   ```javascript
   localStorage.getItem('auth_token')  // Should exist
   ```
3. Try logging out and logging in again

### API calls returning 403 Forbidden
1. Ensure token is being sent:
   ```javascript
   fetch('/api/admin/users', {
     headers: { 'Authorization': `Bearer ${localStorage.getItem('auth_token')}` }
   })
   ```
2. Verify user is admin:
   - Check database: `SELECT is_admin FROM users WHERE email='...';`
   - Check token: Token should end with `|true`

### Settings showing placeholder values instead of actual config
1. Ensure server environment variables are set:
   ```bash
   export MODEL_BACKEND=ollama
   export OLLAMA_MODEL=exaone
   ```
2. Restart server for changes to take effect
3. Check API response:
   ```bash
   curl -H "Authorization: Bearer <token>" http://localhost:5050/api/admin/settings
   ```

---

## Future Enhancements

- [ ] Settings update endpoint (modify environment variables at runtime)
- [ ] Log download functionality
- [ ] Advanced user analytics dashboard
- [ ] Bulk user operations (import/export)
- [ ] Content management (add/edit/delete lessons)
- [ ] System health monitoring
- [ ] Two-factor authentication for admin accounts
- [ ] Admin action audit log viewer
- [ ] User learning progress analytics
