from django import template
from django import forms
from django.http import HttpResponseRedirect

from pirate_forum.models import ForumDimension, DimensionTracker

from search.core import search
from oa_cache.models import ListCache

import datetime

from django.core.validators import URLValidator
from django.core.exceptions import ValidationError

from google.appengine.api import memcache
from google.appengine.ext import deferred

from pirate_ranking.models import get_ranked_list
from pirate_sources.models import URLSource

from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from pirate_core import HttpRedirectException, namespace_get
from pirate_consensus.models import UpDownVote, Consensus, Phase, PhaseLink
from pirate_reputation.models import ReputationDimension
from pirate_forum.models import ForumBlob
from pirate_core.forms import ComboFormFactory
from pirate_topics.models import Topic
from pirate_topics.forms import TopicForm

from pirate_signals.models import aso_rep_event, update_agent

from pirate_badges.models import check_badges

from customtags.decorators import block_decorator
register = template.Library()
block = block_decorator(register)

# this function assignment lets us reuse the same code block a bunch of places
get_namespace = namespace_get('pp_blob')


def get_form(t):
    #grabs the appropriate form for the text input corresponding to type from TYPE_CHOICES
    fd = ForumDimension.objects.get(key=t)
    return fd.get_form(), fd.get_model(), fd.name


def get_models():
    #returns a list of child models for ForumBlob
    return ForumDimension.objects.filter(is_content=True)


@block
def pp_if_forum_blob(context, nodelist, *args, **kwargs):
    """Retrieves blob help text."""
    context.push()
    namespace = get_namespace(context)

    obj = kwargs.pop('object',  None)
    try:
        obj.get_blob_key()
        namespace['is_blob'] = True
    except:
        namespace['is_blob'] = False
    output = nodelist.render(context)
    context.pop()

    return output


@block
def pp_get_blob_help_text(context, nodelist, *args, **kwargs):
    """Retrieves blob help text."""
    context.push()
    namespace = get_namespace(context)

    t = kwargs.pop('dimension', None)

    try:
        fd = ForumDimension.objects.get(key=t)
        namespace['help_text'] = fd.help_text
    except:
        namespace['help_text'] = "KeyError: < " + str(t) + " >Help Text"
    output = nodelist.render(context)
    context.pop()

    return output


@block
def pp_get_blob_dim_readable(context, nodelist, *args, **kwargs):
    """Retrieves blob dimension in human readable format."""
    context.push()
    namespace = get_namespace(context)

    t = kwargs.pop('dimension', None)
    try:
        f = get_form(t)[2]
    except:
        f = 'Error: Human Readable Dimension Not Found'

    namespace['dim_human_readable'] = f

    output = nodelist.render(context)
    context.pop()

    return output


@block
def pp_get_blob_subcontext(context, nodelist, *args, **kwargs):
    """
       This method receives a dimension and object, then parses that for the following
       special cases where dimensions do not provide enough context to the submit.html
       template. 
            *Subtypes: For instance the argument blob has subtypes of Stance. 
                       The specified stance can then be by supplying the 
                       object with the id of that stance. Then the blob form is 
                       aware of the type that should be specifed, so it is not
                       manually necessary for the user to enter stance type.

       THis allows the template author to specify Stance with the dimension, thus
       allowing for links to create preloaded content, for instance "Submit Nay Argument".
       *This template tag must encompass the pp_blob form tag.
    """

    context.push()
    namespace = get_namespace(context)

    dimension = kwargs.pop('dimension', None)

    #ARGUMENT SUBTYPES
    if dimension == 'yea':
        arg, created = Stance.objects.get_or_create(arg="yea")
        namespace['dimension'] = 'arg'
        namespace['sub'] = {'stance': arg}

    elif dimension == 'nay':
        arg, created = Stance.objects.get_or_create(arg="nay")
        namespace['dimension'] = 'arg'
        namespace['sub'] = {'stance': arg}
    else:
        namespace['dimension'] = dimension
        namespace['sub'] = {}

    output = nodelist.render(context)
    context.pop()

    return output


@block
def pp_check_codes(context, nodelist, *args, **kwargs):
    context.push()
    namespace = get_namespace(context)
    codes = memcache.get("rank_update_codes")
    cached_list = []
    if codes is not None:
        for i in codes.keys():
            cached_list.append(str(i) + ':' + str(memcache.get(i)))
        namespace['cache'] = cached_list

    namespace['codes'] = codes
    output = nodelist.render(context)
    context.pop()

    return output


@block
def pp_get_blob_list(context, nodelist, *args, **kwargs):
    """
    These tests are deprecated.

    return output will optionally look for a topic or a
    rng of items in order to further refine the list.

    *Possible Dimension Arguments:
        ** hot: highly intereresting articles based on issue.interest
        ** new: latest content based on submit date
        ** top: those with the most votes
        ** cont: controversial issues that have the userbased divided
        ** numc: Ranked by number of commefrom pirate_issues.models import Topic, Issue, Rankingnts

    The default dimension is "new" when no dimension is specified.

    In order to generate a url that will provide rng information to this tag via
    request.rng, use a url tag of the following form:

    {% url pp-page template="filename.html" start=0 end=20 %}

    In this way, the tag can be invoked as follows:

    {% pp-issue-list topic=topic rng=request.rng dimension="dim" %}
       Do stuff with {{ pp-issue.issue_list }}
    {% endpp-issue-list %}
    """
    context.push()
    namespace = get_namespace(context)

    #user  = kwargs.pop('user',  None)
    parent = kwargs.pop('object', None)
    start = kwargs.pop('start', None)
    end = kwargs.pop('end', None)
    key = kwargs.pop('key', None)
    dimension = kwargs.pop('dimension', None)
    child = kwargs.pop('child', None)

    if isinstance(start, int) and isinstance(end, int):
        try:
            start, end = (int(start), int(end))
        except:
            raise ValueError("The argument 'start=' and 'end=' to the pp_get_blob_list tag must be "
                                 "provided in the form of an int")
    else:
        start, end = (0, 20)

    if dimension is None:
        raise ValueError("The argument 'dimension=' to the pp_get_blob_list tag must be "
                                 "provided in the form of an string")

    if key is None:
        if parent is None:
            key = 'list/' + '/_s' + str(start) + '/_e' + str(end) + '/_d' + str(dimension)
        else:
            ctype = ContentType.objects.get_for_model(parent)
            key = 'list/_t' + str(ctype.pk) + '/_o' + str(parent.pk) + '/_s' + str(start) + '/_e' + str(end) + '/_d' + str(dimension)

    l = ListCache.objects.get(content_type='item', template="children")

    cached_list, tot_items = l.get_or_create_list(key, {}, forcerender=False)

    namespace['count'] = tot_items
    namespace['blob_list'] = cached_list
    namespace['cached'] = False

    #else:
    #    namespace['count'] = cached_list[1]
    #    namespace['blob_list'] = cached_list[0]
    #    namespace['cached'] = True

    #issue list must be empty
    output = nodelist.render(context)
    context.pop()

    return output


@block
def pp_get_forumdimension(context, nodelist, *args, **kwargs):
    '''
    Returns a ForumDimension object with key=dimension
    '''
    context.push()
    namespace = get_namespace(context)

    dimension = kwargs.get('dimension', None)
    try:
        fd = ForumDimension.objects.get(key=dimension)
    except:
        fd = None

    namespace['forumdimension'] = fd

    output = nodelist.render(context)
    context.pop()

    return output


class TypeForm(forms.Form):
    ctype = forms.ModelChoiceField(label=(u'Content Type'),
        queryset=ForumDimension.objects.filter(is_content=True).exclude(is_child=True))


###SOME HELPER FUNCTIONS THAT ARE DEFERRED FOR PP_BLOB_FORM
def defer_dimensiontracker_update(parent, dimension):
    try:
        fd = ForumDimension.objects.get(key=dimension)
        d, is_new = DimensionTracker.objects.get_or_create(object_pk=parent.pk,dimension=fd)
        if is_new:
            d.children = 1
            usc = UserSaltCache(div_id='#sort')
            for ranking_dim in ('hn', 'h', 'n', 'c'):
                context = {'dimension': ranking_dim,'object': parent, 'sort_type': dimension}
                usc.render(context, forcerender=True)
        else:
            d.children = d.children + 1
        d.save()
    except:
        pass
        #forumdimension doesn't work


@block
def pp_blob_form(context, nodelist, *args, **kwargs):
    '''form_id = forms.CharField(widget=forms.HiddenInput(), initial="pp-issue-form")
    This block tag can create or process forms either to create or to modify issues.
    Usage is as follows:

    {% pp_blob_form POST=request.POST path=request.path parent=request.object %}
       Do stuff with {{ pp-issue.form }}.
    {% endpp_blob_form %}

    This form has become a little overloaded.

    '''
    context.push()
    namespace = get_namespace(context)

    POST = kwargs.get('POST', None)
    parent = kwargs.get('parent', None)
    user = kwargs.get('user', None)
    dimension = kwargs.get('dimension', None)
    obj = kwargs.get('object', None)
    sub = kwargs.get('sub', None)
    edit = kwargs.get('edit', None)
    #subcontext imparted to form

    #for editting objects
    if edit and obj is not None:
        blob_form, model, verbose_name = get_form(dimension)
        if POST:
            #save editted form
            form = blob_form(POST, instance=obj)
            blob = form.save()

            if 'link' in form.cleaned_data:
                validate = URLValidator(verify_exists=False)
                contype = ContentType.objects.get_for_model(blob)
                try:
                    validate(form.cleaned_data['link'])
                    if blob.link is not None:
                        blob.link.url = form.cleaned_data['link']
                        blob.link.save()
                        blob.save()
                except ValidationError:
                    newform = blob_form(POST)
                    namespace['form'] = newform
                    if 'http://' not in form.cleaned_data['link']:
                        namespace['errors'] = 'Invalid URL: Make sure it has http://'
                    else:
                        namespace['errors'] = 'Invalid URL: ' + str(form.cleaned_data['link'])
                    output = nodelist.render(context)
                    context.pop()
            content_type = ContentType.objects.get_for_model(obj.__class__)
            path = "/index.html#item" + "/_t" + str(content_type.pk) + "/_o" + str(obj.pk)
            namespace['form_complete'] = True
            namespace['path'] = path
            namespace['form'] = form
        else:
            form = blob_form(instance=obj)
            try:
                if obj.link is not None:
                    form = blob_form(instance=obj, initial={'link': str(obj.link)})
            except:
                pass
            namespace['form'] = form

    elif dimension is not None:
        if parent is not None:
            if ContentType.objects.get_for_model(parent) == ContentType.objects.get_for_model(User):
                parent = None
        blob_form, model, verbose_name = get_form(dimension)
        #get appropriate form

        if POST and user is not None:

            if parent is None and obj is None:
                comboform = ComboFormFactory(TopicForm(POST), blob_form(POST)).ComboForm()
                #load POST
            else:
                comboform = ComboFormFactory(blob_form(POST)).ComboForm()
                #load POST with no PARENT
            for form in comboform._forms:
                if form.is_valid():
                    #if this is a TopicForm, we must extract the parent
                    try:
                        parent = form.cleaned_data['parent']
                        parent.children += 1
                        parent.save()
                    except:
                        blob = form.save(commit=False)
                        blob.user = user
                        blob.parent_pk = parent.pk
                        blob.parent_type = ContentType.objects.get_for_model(parent)

                        if sub is not None:
                            for form_key, value in sub.items():
                                setattr(blob, form_key, value)

                        blob.save()

                        contype = ContentType.objects.get_for_model(blob.__class__)

                        if 'link' in form.cleaned_data:
                            validate = URLValidator(verify_exists=False)
                            try:
                                validate(form.cleaned_data['link'])
                                new_link = URLSource(url=form.cleaned_data['link'], content_type=contype, object_pk=blob.pk, user=user)
                                new_link.save()
                                blob.link = new_link
                                blob.save()
                            except ValidationError:
                                newform = ComboFormFactory(TopicForm(POST, initial={'parent': parent.pk}), blob_form(POST)).ComboForm()
                                namespace['form'] = newform
                                if 'http://' not in form.cleaned_data['link']:
                                    namespace['errors'] = 'Invalid URL: Make sure it has http://'
                                else:
                                    namespace['errors'] = 'Invalid URL: ' + str(form.cleaned_data['link'])
                                output = nodelist.render(context)
                                context.pop()

                                return output

                        #CONSENSUS RELATED DENORMALIZATION
                        # All ForumBlobs have consensus objects attached
                        try:
                            parent_cons = Consensus.objects.get(object_pk=parent.pk)
                            if parent_cons.child_vote_type != None:
                                cvt = parent_cons.child_vote_type
                            else:
                                cvt = ContentType.objects.get_for_model(UpDownVote)
                        except:
                            cvt = ContentType.objects.get_for_model(UpDownVote)

                        cons, is_new = Consensus.objects.get_or_create(content_type=contype,
                                    object_pk=blob.pk,
                                    vote_type=cvt,
                                    parent_pk=blob.parent_pk)

                        if is_new:
                            decision_dt = 0
                            phase_change = 0
                            #create phase object
                            ph = Phase.objects.get_or_create(consensus=cons, curphase=PhaseLink.objects.get(prevphase=None),
                                                                creation_dt=datetime.datetime.now(), decision_dt=decision_dt,
                                                                phase_change_dt=phase_change, complete=False, active=True)

                        aso_rep_event.send(sender=user, event_score=1, user=user, initiator=user, dimension=ReputationDimension.objects.get(name=blob.get_verbose_name()), related_object=cons)
                        update_agent.send(sender=blob, type="content", params=[ContentType.objects.get_for_model(blob.__class__).app_label, verbose_name.lower(), blob.pk])
                        #check badges for this model on creation
                        check_badges(user, model, user)

                        #update the dimensiontracker, used for sorting by content type
                        deferred.defer(defer_dimensiontracker_update, parent, dimension)

                        #if is_new: #if this is a new issue/consensus, send signal for reputation
                        #relationship_event.send(sender=issue,obj=issue,parent=issue.topic)
                        content_type = ContentType.objects.get_for_model(blob.__class__)

                        path = "/index.html#item" + "/_t" + str(content_type.pk) + "/_o" + str(blob.pk)
                        namespace['path'] = path
                        namespace['form_complete'] = True
                        #provide context with extension path
                        #raise HttpRedirectException(HttpResponseRedirect(path))

                else:
                    if not (form == TopicForm() and parent is not None):
                        namespace['errors'] = form.errors
                        form = ComboFormFactory(TopicForm(POST), blob_form(POST)).ComboForm()
                        break

        else:
            blob_form, model, verbose_name = get_form(dimension)
            form = ComboFormFactory(TopicForm(initial={'parent': Topic.objects.get(is_featured=True).pk}), blob_form()).ComboForm()

        namespace['form'] = form
        namespace['POST'] = POST, parent
        namespace['test'] = obj

        #check for optional fields
        has_optional = False
        for k, v in form.fields.items():
            if not v.required:
                has_optional = True
                break
        namespace['optional_fields'] = has_optional

    if parent is not None:
        if isinstance(parent, Topic):
            namespace['parent_summary'] = parent.summary
        if isinstance(parent, ForumBlob):
            namespace['parent_summary'] = parent.summary
        elif isinstance(parent, User):
            namespace['parent_summary'] = parent.username

    output = nodelist.render(context)
    context.pop()

    return output

























@block
def pp_blob_child_dimension(context, nodelist, *args, **kwargs):
    '''Takes an object from the context, identifies the submission
    dimension for it's children, and returns the dimension to the context
    as a str that can be used in a pp_url to redirect to submit.html page
    '''

    context.push()
    namespace = get_namespace(context)

    obj = kwargs.get('object', None)

    try:
        namespace['dimension'] = str(obj.child.get_blob_key())
    except:
        namespace['dimension'] = None

    output = nodelist.render(context)
    context.pop()

    return output


@block
def pp_blob_getchildren(context, nodelist, *args, **kwargs):
    '''Takes an object from the context, identifies the submission
    dimension for it's children, and returns the dimension to the context
    as a str that can be used in a pp_url to redirect to submit.html page
    '''

    context.push()
    namespace = get_namespace(context)

    obj = kwargs.get('object', None)

    if obj.child is not None:
        mm = obj.child.model_class()
        c = mm.objects.filter(parent_pk=obj.pk)
        namespace['children'] = c

    output = nodelist.render(context)
    context.pop()

    return output

@block
def pp_get_contenttypes(context, nodelist, *args, **kwargs):
    '''Renders a list of content types, used
    for sorting the main list by content type.
    '''

    context.push()
    namespace = get_namespace(context)

    dimension = kwargs.get('dimension', None)
    obj = kwargs.get('object', None)
    #user = kwargs.get('user', None)

    fds = ForumDimension.objects.filter(is_content=True)
    out = []

    for fd in fds:
        try:
            d = DimensionTracker.objects.get(dimension=fd, object_pk=obj.pk)
            if d.children > 0:   
                blob_form, model, verbose_name = get_form(fd.key)

                if not fd.is_admin:
                    out.append((fd.key, verbose_name))
        except:
            pass
            
    namespace['content_types'] = out
    output = nodelist.render(context)
    context.pop()

    return output


@block
def pp_show_blobchoices(context, nodelist, *args, **kwargs):
    '''Takes a choice from a list of possible objects that can be created,
        and dynamically loads a form with the required and not required fields.

        Populates the context with a pp_blob.blob_form_type, pp_blob.blob_form,
        and pp_blob.blob_form_html that provide the instance with a form
        and html template for inclusion in the template.
    '''

    context.push()
    namespace = get_namespace(context)

    dimension = kwargs.get('dimension', None)
    obj = kwargs.get('object', None)
    user = kwargs.get('user', None)

    if dimension:
        blob_form, model, verbose_name = get_form(dimension)
        #namespace['help_text'] = model._meta.help_text
    if obj is not None:
        obj_c = ContentType.objects.get_for_model(obj)
        extra = "&_t=" + str(obj_c.id) + "&_o=" + str(obj.pk)
    else:
        extra = ""

    choices = []
    fds = ForumDimension.objects.filter(is_content=True)
    cats = []
    for fd in fds:
        blob_form, model, verbose_name = get_form(fd.key)

        if fd.is_admin and user.is_staff or not fd.is_admin:
            #TODO: IMPLEMENT REAL CONTENTTYPE BASED PERMISSIONS
            if not fd.is_child:
                #solutions and args
                cats.append((fd.name, "/submit.html?_d=" + str(fd.key) + extra, str(fd.key)))

    choices.append(('', cats))

    namespace['choices'] = choices
    output = nodelist.render(context)
    context.pop()

    return output

@block
def pp_search_form(context, nodelist, *args, **kwargs):

    context.push()
    namespace = get_namespace(context)

    POST = kwargs.get('POST', None)
    
    if POST:
        form = SearchForm(POST)
        results = {}
        if form.is_valid():
            search_key = form.cleaned_data['search']
            path = "/index.html#search_results/_r" + str(search_key)
            namespace['path'] = path #provide context with extension path
            raise HttpRedirectException(HttpResponseRedirect(path))
    
    else: form = SearchForm()
    
    namespace['form'] = form
    output = nodelist.render(context)
    context.pop()

    return output

@block
def pp_get_object(context, nodelist, *args, **kwargs):
    """
    Given an object id and model, this returns the object associated.
    """

    context.push()
    namespace = get_namespace(context)
    
    model = kwargs.get('model',None)
    object_pk = kwargs.get('object_pk',None)
    
    content_type   = ContentType.objects.get(pk=int(model))
    obj = content_type.get_object_for_this_type(pk=object_pk)
    
    namespace['content_object'] = obj
    
    output = nodelist.render(context)
    context.pop()

    return output 


@block
def pp_get_search_items(context, nodelist, *args, **kwargs):

    context.push()
    namespace = get_namespace(context)

    search_key = kwargs.get('search_key', None)
    num = 0
    failed = []
    if search_key is not None:
        results = {}
        for fd in get_models():
            try:
                mod = fd.get_model()
                ctype_pk = ContentType.objects.get_for_model(mod).pk
                s = search(mod, search_key)
                results[str(ctype_pk)] = s
                num += len(s)
            except:
                failed.append(mod)

        #search for topics
        s = search(Topic, search_key)
        topics = s
        topic_num = len(s)

        namespace['topics'] = topics
        namespace['num_topics'] = topic_num
        namespace['results'] = results
        namespace['num_results'] = num
        namespace['failed'] = failed

    output = nodelist.render(context)
    context.pop()

    return output


class BlobForm(forms.Form):
    '''
    This form is used to allow creation and modification of issue objects.  
    It extends FormMixin in order to provide a create() class method, which
    is used to process POST, path, and object variables in a consistant way,
    and in order to automatically provide the form with a form_id.
    '''

    #need to grab user from authenticatio
    form_id = forms.CharField(widget=forms.HiddenInput(), initial="pp_blob_form")

    summary = forms.CharField(label="Summary", max_length=100,
              widget=forms.TextInput( 
                attrs={'size':'50', 'class':'inputText'})) 
    description = forms.CharField(widget=forms.Textarea)


class SearchForm(forms.Form):
    search = forms.CharField(widget=forms.TextInput())