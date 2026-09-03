# Lazy Loading

Lazy loading is used in browse mode. The frontend loads bucket roots first, then
loads one folder level at a time.

## Load roots

```http
GET /api/tree/dashboard/{instance_uuid}/children?access=read
Authorization: Bearer <token>
```

```json
{
  "access": "read",
  "parent_id": null,
  "assets": [
    {
      "id": "12",
      "parent": "#",
      "text": "research-data",
      "li_attr": {
        "type": "folder",
        "bucket": "research-data",
        "full_path": "/",
        "has_children": true
      }
    }
  ]
}
```

## Load a folder

```http
GET /api/tree/dashboard/{instance_uuid}/children?access=read&parent_id=12
Authorization: Bearer <token>
```

The response contains only the folder's immediate authorized children.

```json
{
  "access": "read",
  "parent_id": 12,
  "assets": [
    {
      "id": "18",
      "parent": "12",
      "text": "study-a",
      "li_attr": {
        "type": "folder",
        "bucket": "research-data",
        "full_path": "/study-a/",
        "has_children": true
      }
    },
    {
      "id": "file-41",
      "parent": "12",
      "text": "README.txt",
      "li_attr": {
        "type": "file",
        "bucket": "research-data",
        "key": "README.txt"
      }
    }
  ]
}
```

Folder IDs are numeric strings. File IDs start with `file-`. Bucket roots use
`parent: "#"`.

`has_children` tells the frontend whether a folder can be expanded before its
children have been loaded.

## Frontend behavior

When a folder is opened, the frontend:

1. shows a loading spinner;
2. requests the folder's immediate children;
3. merges new nodes into the existing flat node list;
4. marks the folder as loaded;
5. expands the folder.

Each folder is normally loaded once per access tab. Failed requests are not
marked as loaded, so the user can try again.

If a selected read or delete folder loads new children, those children are also
selected. Write mode does not do this because uploads require one selected
destination folder.

## Common responses

- `404`: the folder was not found for this storage instance.
- `403`: Casbin denied access to the parent folder.
- `500`: the backend could not list the instance's buckets.
- `200` with no assets: there are no visible immediate children.

A folder may look empty when it contains items the user is not allowed to see.
