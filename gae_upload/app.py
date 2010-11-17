from google.appengine.api import users
from google.appengine.ext import webapp
from google.appengine.ext import db as datastore
from google.appengine.ext.webapp import template
from google.appengine.ext.webapp.util import run_wsgi_app as run_wsgi

from django.utils import simplejson as json

import cgi


class Experiment(datastore.Model):
  created = datastore.DateTimeProperty(auto_now_add=True)
  owner = datastore.UserProperty()
  title = datastore.StringProperty()
  group_count = datastore.IntegerProperty(default=0)
  counter = datastore.IntegerProperty(default=0)

  def increment_counter(self):
    return datastore.run_in_transaction(increment_experiment_counter, self.key())


class IncrementCounterRequest(datastore.Model):
  created = datastore.DateTimeProperty(auto_now_add=True)
  experiment = datastore.ReferenceProperty(Experiment, collection_name='requests')
  remote_addr = datastore.StringProperty()
  user_agent = datastore.StringProperty()
  return_value = datastore.IntegerProperty()


def increment_experiment_counter(experiment_key):
  experiment = datastore.get(experiment_key)
  index = experiment.counter
  experiment.counter = (experiment.counter + 1) % experiment.group_count
  experiment.put()
  return index


class Handler(webapp.RequestHandler):
  def __str__(self):
    return self.request.url

  def write(self, data):
    self.response.out.write(data)

  def render(self, path, params):
    self.write(template.render(path, params))

  def render_json(self, data):
    self.response.headers['Content-Type'] = 'application/json'

    self.write(json.dumps(data))

  def inspect(self, obj):
    self.write(cgi.escape(repr(obj)))

  def reply(self, code, text):
    self.response.set_status(code)

    self.write(cgi.escape(text))

  def client_error(self, code, message=None):
    if message is None:
      message = webapp.Response.http_status_message(code)

    self.reply(code, message)

  def not_found(self):
    self.client_error(404)


def experiment_required(fn):
  def _fn(self, key, *args, **kwargs):
    try:
      self.experiment = Experiment.get(key)
    except datastore.BadKeyError:
      return self.not_found()

    return fn(self, key, *args, **kwargs)

  return _fn


class ExperimentForm(Handler):
  def get(self):
    self.render('priv/experiment_form.html', {
      'user': users.get_current_user()
    , 'self': self
    })

  def post(self):
    experiment = Experiment()
    experiment.owner = users.get_current_user()
    experiment.title = self.request.get('title')
    experiment.group_count = int(self.request.get('group_count'))
    experiment.put()

    self.redirect('/exp/' + str(experiment.key()))


class ExperimentCounter(Handler):
  @experiment_required
  def get(self, key):
    self.render('priv/experiment_counter.html', {
      'experiment': self.experiment
    })

  @experiment_required
  def post(self, key):
    index = self.experiment.increment_counter()

    self.response.set_status(202) # Accepted

    self.render_json({'group': index})


def handlers():
  return [
    ('/', ExperimentForm)
  , (r'/exp/(.*)', ExperimentCounter)
  ]


def application():
  return webapp.WSGIApplication(handlers(), debug=True)


def main():
  run_wsgi(application())


if __name__ == '__main__':
  main()
