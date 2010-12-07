import uuid
from hashlib import md5
from datetime import datetime
from django.db import models
from django.utils.translation import ugettext_lazy as _
from django.contrib.auth.models import User
from django.template.defaultfilters import slugify

from timezones.fields import TimeZoneField
from entities.models import Entity
from events.managers import EventManager, RegistrantManager, EventTypeManager
from perms.models import TendenciBaseModel
from meta.models import Meta as MetaTags
from events.module_meta import EventMeta

from invoices.models import Invoice

class TypeColorSet(models.Model):
    """
    Colors representing a type [color-scheme]
    The values can be hex or literal color names
    """
    fg_color = models.CharField(max_length=20)
    bg_color = models.CharField(max_length=20)
    border_color = models.CharField(max_length=20)

    def __unicode__(self):
        return '%s #%s' % (self.pk, self.bg_color)

class Type(models.Model):
    
    """
    Types is a way of grouping events
    An event can only be one type
    A type can have multiple events
    """
    name = models.CharField(max_length=50)
    slug = models.SlugField(max_length=50, editable=False)
    color_set = models.ForeignKey('TypeColorSet')

    objects = EventTypeManager()

    @property
    def fg_color(self):
        return '#%s' % self.color_set.fg_color
    @property
    def bg_color(self):
        return '#%s' % self.color_set.bg_color
    @property
    def border_color(self):
        return '#%s' % self.color_set.border_color

    def __unicode__(self):
        return self.name

    def save(self, *args, **kwargs):
        self.slug = slugify(self.name)
        super(self.__class__, self).save(*args, **kwargs)

class Place(models.Model):
    """
    Event Place (location)
    An event can only be in one place
    A place can be used for multiple events
    """
    name = models.CharField(max_length=150, blank=True)
    description = models.TextField(blank=True)

    # offline location
    address = models.CharField(max_length=150, blank=True)
    city = models.CharField(max_length=150, blank=True)
    state = models.CharField(max_length=150, blank=True)
    zip = models.CharField(max_length=150, blank=True)
    country = models.CharField(max_length=150, blank=True)

    # online location
    url = models.URLField(blank=True)

    def __unicode__(self):
        str_place = '%s %s %s %s %s' % (
            self.name, self.address, ', '.join(self.city_state()), self.zip, self.country)
        return unicode(str_place.strip())

    def city_state(self):
        return [s for s in (self.city, self.state) if s]

class Registrant(models.Model):
    """
    Event registrant.
    An event can have multiple registrants.
    A registrant can go to multiple events.
    A registrant is static information.
    The names do not change nor does their information
    This is the information that was used while registering
    """
    registration = models.ForeignKey('Registration')
    user = models.ForeignKey(User, blank=True, null=True)
    
    name = models.CharField(max_length=100)
    mail_name = models.CharField(max_length=100)
    address = models.CharField(max_length=200)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    zip = models.CharField(max_length=50)
    country = models.CharField(max_length=100)

    phone = models.CharField(max_length=50)
    email = models.CharField(max_length=100)
    groups = models.CharField(max_length=100)

    position_title = models.CharField(max_length=100)
    company_name = models.CharField(max_length=100)

    cancel_dt = models.DateTimeField(editable=False, null=True)

    create_dt = models.DateTimeField(auto_now_add=True)
    update_dt = models.DateTimeField(auto_now=True)
    
    objects = RegistrantManager()

    @property
    def lastname_firstname(self):
        
        name_list = [n for n in self.name.split() if n]
        prefix = first = middle = last = suffix = ""

        if len(name_list) == 5:
            prefix, first, middle, last, suffix = name_list
        elif len(name_list) == 4:
            first, middle, last, suffix = name_list
        elif len(name_list) == 3:
            first, middle, last = name_list
        elif len(name_list) == 2:
            first, last = name_list
        elif len(name_list) == 1:
            first = name_list[0]
        else:
            first = self.name

        if first and last:
            return "%s, %s" % (last, first)
        elif first:
            return "%s" % first


        

    @classmethod
    def event_registrants(cls, event=None):

        return cls.objects.filter(
            registration__event = event,
            cancel_dt = None,
        )

    @property
    def hash(self):
        return md5(".".join([str(self.registration.event.pk), self.email])).hexdigest()

    @models.permalink
    def hash_url(self):
        return ('membership.application_confirmation', [self.registration.event.pk, self.hash])

    class Meta:
        permissions = (("view_registrant","Can view registrant"),)

    @models.permalink
    def get_absolute_url(self):
        return ('event.registration_confirmation', [self.registration.event.pk, self.pk])

class Registration(models.Model):

    guid = models.TextField(max_length=40, editable=False, default=uuid.uuid1)
    event = models.ForeignKey('Event') # dynamic (should be static)

    reminder = models.BooleanField(default=False)
    note = models.TextField(blank=True)

    invoice = models.ForeignKey(Invoice, blank=True, null=True)

    # TODO: Payment-Method must be soft-deleted
    # so that it may always be referenced
    payment_method = models.ForeignKey('PaymentMethod', null=True)
    amount_paid = models.DecimalField(_('Amount Paid'), max_digits=21, decimal_places=2)

    creator = models.ForeignKey(User, related_name='created_registrations', null=True)
    owner = models.ForeignKey(User, related_name='owned_registrations', null=True)
    create_dt = models.DateTimeField(auto_now_add=True)
    update_dt = models.DateTimeField(auto_now=True)


    @property
    def registrant(self):
        """
        Gets primary registrant.
        Get first registrant w/ email address
        Order by insertion (primary key)
        """

        try:
            registrant = self.registrant_set.filter(
                email__isnull=False).order_by("pk")[0]
        except:
            registrant = None

        return registrant

    def save_invoice(self, *args, **kwargs):
        status_detail = kwargs.get('status_detail', 'estimate')

        try: # get invoice
            invoice = Invoice.objects.get(
                invoice_object_type = 'calendarevents',
                invoice_object_type_id = self.pk,
            )
        except: # else; create invoice
            # cannot use get_or_create method
            # because too many fields are required
            invoice = Invoice()
            invoice.invoice_object_type = 'event_registration'
            invoice.invoice_object_type_id = self.pk

        # update invoice with details
        invoice.estimate = True
        invoice.status_detail = status_detail
        invoice.subtotal = self.amount_paid
        invoice.total = self.amount_paid
        invoice.balance = 0
        invoice.due_date = datetime.now()
        invoice.ship_date = datetime.now()
        invoice.save()

        self.invoice = invoice

        self.save()

        return invoice

# TODO: use shorter name
class RegistrationConfiguration(models.Model):
    """
    Event registration
    Extends the event model
    """
    # TODO: do not use fixtures, use RAWSQL to prepopulate
    # TODO: set widget here instead of within form class
    payment_method = models.ManyToManyField('PaymentMethod')
    
    early_price = models.DecimalField(_('Early Price'), max_digits=21, decimal_places=2, default=0)
    regular_price = models.DecimalField(_('Regular Price'), max_digits=21, decimal_places=2, default=0)
    late_price = models.DecimalField(_('Late Price'), max_digits=21, decimal_places=2, default=0)

    early_dt = models.DateTimeField(_('Early Date'))
    regular_dt = models.DateTimeField(_('Regular Date'))
    late_dt = models.DateTimeField(_('Late Date'))

    limit = models.IntegerField(default=0)
    enabled = models.BooleanField(default=False)

    create_dt = models.DateTimeField(auto_now_add=True)
    update_dt = models.DateTimeField(auto_now=True)

    

    def __init__(self, *args, **kwargs):
        super(self.__class__, self).__init__(*args, **kwargs)

        if hasattr(self,'event'):
        # registration_configuration might not be attached to an event yet
            self.PERIODS = {
                'early': (self.early_dt, self.regular_dt),
                'regular': (self.regular_dt, self.late_dt),
                'late': (self.late_dt, self.event.start_dt),
            }
        else:
            self.PERIODS = None

    def available(self):
        if not self.enabled:
            return False

        if hasattr(self, 'event'):
            if datetime.now() > self.event.end_dt:
                return False

        return True

    @property
    def price(self):
        price = 0.00
        for period in self.PERIODS:
            if self.PERIODS[period][0] <= datetime.now() <= self.PERIODS[period][1]:
                price = self.price_from_period(period)

        return price

    def price_from_period(self, period):

        if period in self.PERIODS:
            return getattr(self, '%s_price' % period)
        else: return None

    @property
    def is_open(self):
        status = [
            self.enabled,
            self.within_time,
        ]
        return all(status)

    @property
    def within_time(self):
        for period in self.PERIODS:
            if self.PERIODS[period][0] <= datetime.now() <= self.PERIODS[period][1]:
                return True
        return False
    


class Payment(models.Model):
    """
    Event registration payment
    Extends the registration model
    """
    registration = models.OneToOneField('Registration')

class PaymentMethod(models.Model):
    """
    This will hold available payment methods
    Default payment methods are 'Credit Card, Cash and Check.'
    Pre-populated via fixtures
    Soft Deletes required; For historical purposes.
    """
    label = models.CharField(max_length=50, blank=False)

    def __unicode__(self):
        return self.label

#class PaymentPeriod(models.Model):
#    """
#    Defines the time-range and price a registrant must pay.
#    e.g. (early price, regular price, late price) 
#    """
#    label = models.CharField(max_length=50)
#    start_dt = models.DateTimeField()
#    end_dt = models.DateTimeField()
#    price = models.DecimalField(max_digits=21, decimal_places=2)
#    registration_confirmation = models.ForeignKey('RegistrationConfiguration', related_name='payment_period')

    # TODO: price per group
    # anonymous (is not a group or is a dynamic group)
    # registered (is not a group or is a dynamic group)
#    anon_price = models.DecimalField(max_digits=21, decimal_places=2)
#    auth_price = models.DecimalField(max_digits=21, decimal_places=2)
#    group_price = models.ForeignKey('GroupPrice') # not the same as group-pricing

#    def __unicode__(self):
#        return self.label


class Sponsor(models.Model):
    """
    Event sponsor
    Event can have multiple sponsors
    Sponsor can contribute to multiple events
    """
    event = models.ManyToManyField('Event')

class Discount(models.Model):
    """
    Event discount
    Event can have multiple discounts
    Discount can only be associated with one event
    """
    event = models.ForeignKey('Event')
    name = models.CharField(max_length=50)
    code = models.CharField(max_length=50)

class Organizer(models.Model):
    """
    Event organizer
    Event can have multiple organizers
    Organizer can maintain multiple events
    """
    event = models.ManyToManyField('Event', blank=True)
    user = models.OneToOneField(User, blank=True, null=True)
    name = models.CharField(max_length=100, blank=True) # static info.
    description = models.TextField(blank=True) # static info.

    def __unicode__(self):
        return self.name    

class Speaker(models.Model):
    """
    Event speaker
    Event can have multiple speakers
    Speaker can attend multiple events
    """
    event = models.ManyToManyField('Event', blank=True)
    user = models.OneToOneField(User, blank=True, null=True)
    name = models.CharField(max_length=100, blank=True) # static info.
    description = models.TextField(blank=True) # static info.
    
    def __unicode__(self):
        return self.name

class Event(TendenciBaseModel):
    """
    Calendar Event
    """
    guid = models.CharField(max_length=40, editable=False, default=uuid.uuid1)
    entity = models.ForeignKey(Entity, blank=True, null=True)

    type = models.ForeignKey(Type, blank=True, null=True)

    title = models.CharField(max_length=150, blank=True)
    description = models.TextField(blank=True)

    all_day = models.BooleanField()
    start_dt = models.DateTimeField(default=datetime.now())
    end_dt = models.DateTimeField(default=datetime.now())
    timezone = TimeZoneField(_('Time Zone'))

    place = models.ForeignKey('Place', null=True)
    registration_configuration = models.OneToOneField('RegistrationConfiguration', null=True, editable=False)

    private = models.BooleanField() # hide from lists
    password = models.CharField(max_length=50, blank=True)

    # html-meta tags
    meta = models.OneToOneField(MetaTags, null=True)

    objects = EventManager()

    class Meta:
        permissions = (("view_event","Can view event"),)

    def get_meta(self, name):
        """
        This method is standard across all models that are
        related to the Meta model.  Used to generate dynamic
        methods coupled to this instance.
        """    
        return EventMeta().get_meta(self, name)

    def is_registrant(self, user):
        return Registration.objects.filter(
            event=self.event, registrant=user).exists()

    @models.permalink
    def get_absolute_url(self):
        return ("event", [self.pk])

    def __unicode__(self):
        return self.title

    # this function is to display the event date in a nice way. 
    # example format: Thursday, August 12, 2010 8:30 AM - 05:30 PM - GJQ 8/12/2010
    def dt_display(self, format_date='%a, %b %d, %Y', format_time='%I:%M %p'):
        from base.utils import format_datetime_range
        return format_datetime_range(self.start_dt, self.end_dt, format_date, format_time)
