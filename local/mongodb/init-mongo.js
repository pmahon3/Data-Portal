// db = db.getSiblingDB("admin")
db = db.getSiblingDB(process.env.MONGO_INITDB_ROOT_USERNAME);
// move to the admin db - always created in Mongo

// db.auth("rootUser", "rootPassword");
// db.auth("admin", "1q2w3e4r");
db.auth(process.env.MONGO_INITDB_ROOT_USERNAME, process.env.MONGO_INITDB_ROOT_PASSWORD)
// log as root admin if you decided to authenticate in your docker-compose file...

// db = db.getSiblingDB('DB_test');
db = db.getSiblingDB('inn_mongo');
// create and move to your new database

db.createUser({
'user': process.env.MONGO_INITDB_ROOT_USERNAME, // "admin",
'pwd': process.env.MONGO_INITDB_ROOT_PASSWORD, // "1q2w3e4r",
'roles': [{
    'role': 'dbOwner',
    'db':  'inn_mongo'
    }]});
// user created
db.createCollection('initial_collection');
// add new collection
