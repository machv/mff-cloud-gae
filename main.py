import cgi
import datetime
import urllib
import webapp2
import json

from datetime import datetime

from google.appengine.ext import db
from google.appengine.api import users
from google.appengine.api import taskqueue
from google.appengine.api import urlfetch

import jinja2
import os

JINJA_ENVIRONMENT = jinja2.Environment(
    loader=jinja2.FileSystemLoader(os.path.dirname(__file__)))

class Greeting(db.Model):
  """Models an individual Guestbook entry with an author, content, and date."""
  author = db.StringProperty()
  content = db.StringProperty(multiline=True)
  date = db.DateTimeProperty(auto_now_add=True)

class Canteen(db.Model):
  Id = db.IntegerProperty()
  Name = db.StringProperty()
  Address = db.StringProperty()
  Location = db.GeoPtProperty()
  Latitude = db.FloatProperty()
  Longitude = db.FloatProperty()

class Menu(db.Model):
  Id = db.IntegerProperty()
  Date = db.DateProperty()
  CanteenId = db.IntegerProperty()
  Name = db.StringProperty()
  Weight = db.StringProperty()
  StudentPrice = db.FloatProperty()
  FullPrice = db.FloatProperty()
  Order = db.IntegerProperty()

class DishCount(db.Model):
  DishId = db.IntegerProperty()
  CanteenId = db.IntegerProperty()
  Count = db.IntegerProperty()
  Date = db.DateTimeProperty(auto_now_add=True)

def guestbook_key(guestbook_name=None):
  """Constructs a Datastore key for a Guestbook entity with guestbook_name."""
  return db.Key.from_path('Guestbook', guestbook_name or 'default_guestbook')

class MenuPage(webapp2.RequestHandler):
  def get(self):
      #canteen = self.request.get('canteen')
      
      canteen = db.GqlQuery("SELECT * FROM Canteen WHERE Id = :1", int(self.request.get('canteen'))).fetch(1)[0]
      
      self.response.write(canteen)
      
      menu = db.GqlQuery("SELECT * FROM Menu " +
                         "WHERE CanteenId >= :1 " +
                         "AND Day >= :2 " +
                         "ORDER BY Day, Order", canteen.Id, datetime.now().date())

      template_values = {
            'canteen': canteen,
            'menu': menu,
        }
      
      template = JINJA_ENVIRONMENT.get_template('detail.html')
      self.response.write(template.render(template_values))


class MainPage(webapp2.RequestHandler):
  def get(self):
      canteens = db.GqlQuery("SELECT * FROM Canteen")

      template_values = {
            'canteens': canteens,
        }
      
      template = JINJA_ENVIRONMENT.get_template('index.html')
      self.response.write(template.render(template_values))


class Counter(db.Model):
    count = db.IntegerProperty(indexed=False)

class EnqueueLoader(webapp2.RequestHandler):
    def get(self):
         # Add the task to the default queue.
        taskqueue.add(url='/loader', params={'load': 'all'})

        self.redirect('/')

class MenuLoader(webapp2.RequestHandler):
    def post(self): # should run at most 1/s
        key = self.request.get('key')

# store menu in transaction -> menu will appear day by day
@db.transactional
def storeMenu(canteenId, dishes):
      for menu in day["Dishes"]:
          dish = Menu(Date=datetime.strptime(day["Date"], '%Y-%m-%d').date(),
                      CanteenId=canteen.Id,
                      Id=menu["Id"],
                      Name=menu["Name"],
                      Weight=menu["Weight"],
                      StudentPrice=float(menu["StudentPrice"]),
                      FullPrice=float(menu["FullPrice"]),
                      Order=menu["Order"])
          dish.put()



class SyncMenus(webapp2.RequestHandler):
    def get(self):
        # load menu for each canteen 
        canteens = db.GqlQuery("SELECT * FROM Canteen")
        for canteen in canteens:
            self.response.out.write(canteen.Name)
            
            url = 'http://menzy.wladik.net/api/1.0/menza/' + str(canteen.Id) + '/menu.json'  
            result = urlfetch.fetch(url)

            days = json.loads(result.content)
            for day in days:
              self.response.out.write("<hr>" + day["Date"] + "<br>")
              storeMenu(canteen.Id, day["Dishes"])
                                        
class InitializeCanteens(webapp2.RequestHandler):
    def get(self):
        # loads list of canteens
        url = 'http://menzy.wladik.net/api/1.0/menzy/list.json'  
        result = urlfetch.fetch(url)
        if result.status_code == 200:
          # remove existing
          existingCanteens = db.GqlQuery("SELECT * FROM Canteen")
          db.delete(existingCanteens)

          # and load new from API server
          i = 0
          canteens = json.loads(result.content)
          for canteenId in canteens:
             canteen = Canteen(Id=canteens[canteenId]['Id'],
                               Name=canteens[canteenId]['Name'],
                               Address=canteens[canteenId]['Address'],
                               Latitude=canteens[canteenId]['Location']['Latitude'],
                               Longitude=canteens[canteenId]['Location']['Longitude'],
                               Location=str(canteens[canteenId]['Location']['Latitude']) + ',' + str(canteens[canteenId]['Location']['Latitude']))
             canteen.put()
             i += 1
          
          self.response.out.write(str(i) + " canteens loaded.")  

class Guestbook(webapp2.RequestHandler):
  def post(self):
    # We set the same parent key on the 'Greeting' to ensure each greeting is in
    # the same entity group. Queries across the single entity group will be
    # consistent. However, the write rate to a single entity group should
    # be limited to ~1/second.
    guestbook_name = self.request.get('guestbook_name')
    greeting = Greeting(parent=guestbook_key(guestbook_name))

    if users.get_current_user():
      greeting.author = users.get_current_user().nickname()

    greeting.content = self.request.get('content')
    greeting.put()
    self.redirect('/?' + urllib.urlencode({'guestbook_name': guestbook_name}))


app = webapp2.WSGIApplication([('/', MainPage),
                               ('/menu', MenuPage),
                               ('/init', InitializeCanteens),
                               ('/sync', SyncMenus),
                               ('/save', EnqueueLoader),
                               ('/loader', MenuLoader),
                               ('/sign', Guestbook)],
                              debug=True)
