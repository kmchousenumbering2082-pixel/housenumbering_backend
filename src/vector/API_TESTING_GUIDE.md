# Vector Layer & Feature Collection APIs - Testing Guide

## Base URL
```
http://localhost:8000/vector
```

## Authentication
All endpoints except GET require authentication. Include the authentication token in the header:
```
Authorization: Bearer <your_access_token>
```

---

## API ENDPOINTS

### 1. VECTOR LAYER ENDPOINTS

#### 1.1 Create Vector Layer
**POST** `/layers`

**Request Body:**
```json
{
  "name_en": "Building Outlines",
  "name_ne": "घर को आउटलाइन",
  "layer_type": "polygon",
  "attr_data": {
    "source": "survey_2024",
    "version": "1.0"
  },
  "style_value": "red",
  "label_value": "buildings",
  "is_public": true,
  "display_on_map": true
}
```

**Response:** 201 Created
```json
{
  "id": 1,
  "name_en": "Building Outlines",
  "name_ne": "घर को आउटलाइन",
  "layer_type": "polygon",
  "attr_data": {"source": "survey_2024", "version": "1.0"},
  "style_value": "red",
  "label_value": "buildings",
  "is_public": true,
  "display_on_map": true,
  "created_by": 1,
  "updated_by": 1,
  "timestamp": "2024-04-05T10:30:00",
  "features": []
}
```

**cURL Command:**
```bash
curl -X POST http://localhost:8000/vector/layers \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "name_en": "Building Outlines",
    "name_ne": "घर को आउटलाइन",
    "layer_type": "polygon",
    "attr_data": {"source": "survey_2024"},
    "style_value": "red",
    "label_value": "buildings",
    "is_public": true,
    "display_on_map": true
  }'
```

---

#### 1.2 List Vector Layers
**GET** `/layers`

**Query Parameters:**
- `skip`: Number of records to skip (default: 0)
- `limit`: Number of records to return (default: 10)
- `layer_type`: Filter by type (polygon, line, point)
- `is_public`: Filter by public status (true/false)
- `display_on_map`: Filter by map display status (true/false)
- `search`: Search in name_en or name_ne
- `sort_by`: Field to sort by (default: id)
- `order`: Sort order - asc or desc (default: asc)

**cURL Command:**
```bash
# List all layers
curl -X GET "http://localhost:8000/vector/layers" \
  -H "Authorization: Bearer YOUR_TOKEN"

# List with filters
curl -X GET "http://localhost:8000/vector/layers?layer_type=polygon&is_public=true&search=Building&limit=20&order=desc" \
  -H "Authorization: Bearer YOUR_TOKEN"

# List with pagination
curl -X GET "http://localhost:8000/vector/layers?skip=10&limit=5" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

---

#### 1.3 Get Single Vector Layer
**GET** `/layers/{layer_id}`

**cURL Command:**
```bash
curl -X GET "http://localhost:8000/vector/layers/1" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

**Response:** 200 OK (Same as list response with all features)

---

#### 1.4 Update Vector Layer
**PATCH** `/layers/{layer_id}`

**Request Body (all fields optional):**
```json
{
  "name_en": "Building Outlines Updated",
  "name_ne": "घर को आउटलाइन अपडेट",
  "layer_type": "polygon",
  "is_public": false,
  "display_on_map": false
}
```

**cURL Command:**
```bash
curl -X PATCH http://localhost:8000/vector/layers/1 \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "name_en": "Building Outlines Updated",
    "display_on_map": false
  }'
```

---

#### 1.5 Delete Vector Layer
**DELETE** `/layers/{layer_id}`

**cURL Command:**
```bash
curl -X DELETE http://localhost:8000/vector/layers/1 \
  -H "Authorization: Bearer YOUR_TOKEN"
```

**Response:** 204 No Content

---

#### 1.6 Get Features Count in Layer
**GET** `/layers/{layer_id}/features-count`

**cURL Command:**
```bash
curl -X GET "http://localhost:8000/vector/layers/1/features-count" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

**Response:** 200 OK
```json
{
  "layer_id": 1,
  "feature_count": 145
}
```

---

### 2. FEATURE COLLECTION ENDPOINTS

#### 2.1 Create Feature
**POST** `/features`

**Request Body:**
```json
{
  "vector_layer_id": 1,
  "attr_data": {
    "building_type": "residential",
    "floors": 3,
    "owner": "John Doe"
  },
  "geom": "{\"type\": \"Polygon\", \"coordinates\": [[[85.3, 27.7], [85.31, 27.7], [85.31, 27.71], [85.3, 27.71], [85.3, 27.7]]]}",
  "style_value": "blue",
  "label_value": "House-001"
}
```

**Response:** 201 Created
```json
{
  "id": 1,
  "vector_layer_id": 1,
  "attr_data": {"building_type": "residential", "floors": 3, "owner": "John Doe"},
  "geom": "...",
  "style_value": "blue",
  "label_value": "House-001",
  "created_by": 1,
  "updated_by": 1,
  "is_deleted": false,
  "timestamp": "2024-04-05T10:35:00"
}
```

**cURL Command:**
```bash
curl -X POST http://localhost:8000/vector/features \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "vector_layer_id": 1,
    "attr_data": {
      "building_type": "residential",
      "floors": 3,
      "owner": "John Doe"
    },
    "style_value": "blue",
    "label_value": "House-001"
  }'
```

---

#### 2.2 List Features
**GET** `/features`

**Query Parameters:**
- `skip`: Number of records to skip (default: 0)
- `limit`: Number of records to return (default: 10)
- `vector_layer_id`: Filter by layer ID
- `is_deleted`: Include deleted features (null = exclude deleted)
- `search`: Search in label_value or style_value
- `sort_by`: Field to sort by (default: id)
- `order`: Sort order - asc or desc (default: asc)

**cURL Command:**
```bash
# List all active features
curl -X GET "http://localhost:8000/vector/features" \
  -H "Authorization: Bearer YOUR_TOKEN"

# List features in specific layer with filters
curl -X GET "http://localhost:8000/vector/features?vector_layer_id=1&limit=50&order=desc" \
  -H "Authorization: Bearer YOUR_TOKEN"

# Search features
curl -X GET "http://localhost:8000/vector/features?search=House&is_deleted=false" \
  -H "Authorization: Bearer YOUR_TOKEN"

# Include deleted features
curl -X GET "http://localhost:8000/vector/features?is_deleted=true&vector_layer_id=1" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

---

#### 2.3 Get Single Feature
**GET** `/features/{feature_id}`

**cURL Command:**
```bash
curl -X GET "http://localhost:8000/vector/features/1" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

---

#### 2.4 Update Feature
**PATCH** `/features/{feature_id}`

**Request Body (all fields optional):**
```json
{
  "attr_data": {
    "building_type": "commercial",
    "floors": 5
  },
  "label_value": "House-001-Updated",
  "style_value": "red"
}
```

**cURL Command:**
```bash
curl -X PATCH http://localhost:8000/vector/features/1 \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "attr_data": {
      "building_type": "commercial",
      "floors": 5
    },
    "label_value": "House-001-Updated"
  }'
```

---

#### 2.5 Soft Delete Feature
**DELETE** `/features/{feature_id}`

Marks the feature as deleted without removing from database.

**cURL Command:**
```bash
curl -X DELETE http://localhost:8000/vector/features/1 \
  -H "Authorization: Bearer YOUR_TOKEN"
```

**Response:** 204 No Content

---

#### 2.6 Permanently Delete Feature
**DELETE** `/features/{feature_id}/permanent`

Completely removes the feature from database.

**cURL Command:**
```bash
curl -X DELETE http://localhost:8000/vector/features/1/permanent \
  -H "Authorization: Bearer YOUR_TOKEN"
```

**Response:** 204 No Content

---

#### 2.7 Restore Feature
**POST** `/features/{feature_id}/restore`

Restores a soft-deleted feature.

**cURL Command:**
```bash
curl -X POST http://localhost:8000/vector/features/1/restore \
  -H "Authorization: Bearer YOUR_TOKEN"
```

**Response:** 200 OK (Returns the restored feature object)

---

## TESTING WORKFLOW

### Step 1: Get Authentication Token
First, register/login to get a token:
```bash
curl -X POST http://localhost:8000/auth/signup \
  -H "Content-Type: multipart/form-data" \
  -F "email=test@example.com" \
  -F "password=Test@123" \
  -F "username=testuser"
```

Store the returned `access_token` for subsequent requests.

### Step 2: Create a Vector Layer
```bash
curl -X POST http://localhost:8000/vector/layers \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "name_en": "Test Layer",
    "name_ne": "परीक्षण लेयर",
    "layer_type": "polygon",
    "is_public": true,
    "display_on_map": true
  }'
```

Save the returned `layer_id`.

### Step 3: Create Multiple Features
```bash
# Feature 1
curl -X POST http://localhost:8000/vector/features \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "vector_layer_id": 1,
    "label_value": "Feature-001",
    "attr_data": {"type": "test", "value": 100}
  }'

# Feature 2
curl -X POST http://localhost:8000/vector/features \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "vector_layer_id": 1,
    "label_value": "Feature-002",
    "attr_data": {"type": "test", "value": 200}
  }'
```

### Step 4: Test Filtering
```bash
# Get features by label search
curl -X GET "http://localhost:8000/vector/features?search=Feature-001" \
  -H "Authorization: Bearer YOUR_TOKEN"

# Get layer with all features
curl -X GET "http://localhost:8000/vector/layers/1" \
  -H "Authorization: Bearer YOUR_TOKEN"

# Check feature count
curl -X GET "http://localhost:8000/vector/layers/1/features-count" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Step 5: Test Updates
```bash
curl -X PATCH http://localhost:8000/vector/features/1 \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "label_value": "Feature-001-Updated",
    "attr_data": {"type": "updated", "value": 150}
  }'
```

### Step 6: Test Deletion & Restoration
```bash
# Soft delete
curl -X DELETE http://localhost:8000/vector/features/1 \
  -H "Authorization: Bearer YOUR_TOKEN"

# List with deleted=true to verify it's deleted
curl -X GET "http://localhost:8000/vector/features?is_deleted=true" \
  -H "Authorization: Bearer YOUR_TOKEN"

# Restore
curl -X POST http://localhost:8000/vector/features/1/restore \
  -H "Authorization: Bearer YOUR_TOKEN"

# Verify restoration
curl -X GET "http://localhost:8000/vector/features/1" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

---

## EXPECTED RESPONSE CODES

| Status | Meaning |
|--------|---------|
| 200 | Success (GET, PATCH, POST for restore) |
| 201 | Created (POST) |
| 204 | No Content (DELETE) |
| 400 | Bad Request (invalid data) |
| 401 | Unauthorized (missing token) |
| 404 | Not Found (resource doesn't exist) |
| 422 | Unprocessable Entity (invalid field format) |
| 500 | Server Error |

---

## FEATURES IMPLEMENTED

✅ **Create, Read, Update**, Delete (CRUD) for both Vector Layers and Features  
✅ **Soft Delete** - Mark as deleted without removing  
✅ **Permanent Delete** - Remove from database  
✅ **Restore** - Restore soft-deleted features  
✅ **Filtering** - By layer type, public status, deletion status, search terms  
✅ **Pagination** - skip/limit parameters for all list endpoints  
✅ **Sorting** - Sort by any field, ascending or descending  
✅ **Nested Data** - Features automatically loaded with layers  
✅ **Audit Trail** - created_by, updated_by, timestamp tracking  
✅ **Feature Count** - Get count of features in a layer  
✅ **Validation** - Vector layer existence check when creating features  
✅ **Authentication** - All write operations require auth  
