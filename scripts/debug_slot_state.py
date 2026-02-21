from config import MONGO_URI
from pymongo import MongoClient

client = MongoClient(MONGO_URI)
db = client.get_database()

day = '2026-02-22'
slot = '7:00am'

print('Rafts:')
for r in db.rafts.find({'day': day, 'slot': slot}).sort('raft_id', 1):
    print(r)

print('\nBookings:')
for b in db.bookings.find({'date': day, 'slot': slot}):
    print(b)
