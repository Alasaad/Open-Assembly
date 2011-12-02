from django import template
from django import forms

from pirate_permissions.models import Permission, PermissionsGroup

import re
from django.contrib.contenttypes.models import ContentType

from markitup.widgets import MarkItUpWidget

from pirate_topics.models import Topic, MyGroup, GroupSettings
from pirate_core.views import namespace_get

from customtags.decorators import block_decorator
register = template.Library()
block = block_decorator(register)

get_namespace = namespace_get('pp_topic')


@block
def pp_get_topic_if_content(context, nodelist, *args, **kwargs):

    context.push()
    namespace = get_namespace(context)

    obj = kwargs.pop('object', None)

    ctype_obj = ContentType.objects.get_for_model(obj)
    ctype = ContentType.objects.get_for_model(Topic)

    ret = None
    if ctype == ctype_obj:
        #if object is a topic
        ret = obj
    elif obj.parent is not None:
        ret = obj.parent

    namespace['object'] = ret
    output = nodelist.render(context)
    context.pop()

    return output


@block
def pp_get_topic(context, nodelist, *args, **kwargs):

    context.push()
    namespace = get_namespace(context)

    obj = kwargs.pop('object', None)
    object_pk = kwargs.pop('object_pk', None)
    topicname = kwargs.pop('topicname', None)

    if topicname is not None:
        try:
            topic = Topic.objects.get(summary=topicname)
        except:
            topic = None
    else:
        topic = None
    parent = None
    if obj is not None:
        try:
            if obj.get_child_blob_key():
                parent = obj
        except:
            try:
                if obj.parent.summary != '__NULL__':
                    parent = obj.parent
                else:
                    parent = obj
            except:
                pass

    if object_pk is not None:
        top = Topic.objects.get(pk=int(object_pk))
    else:
        top = None

    namespace['parent'] = parent
    namespace['topic'] = topic
    namespace['object'] = top

    output = nodelist.render(context)
    context.pop()

    return output


@block
def pp_add_mygroup(context, nodelist, *args, **kwargs):

    context.push()
    namespace = get_namespace(context)

    topic = kwargs.pop('topic', None)
    user = kwargs.pop('user', None)

    mygroup, is_new = MyGroup.objects.get_or_create(user=user, topic=topic)
    topic.group_members += 1
    topic.save()

    output = nodelist.render(context)
    context.pop()

    return output


@block
def pp_get_topic_hierarchy(context, nodelist, *args, **kwargs):
    """
    This block tag will grab the parent of a topic. Each Topic object contains
    a parent or if a root node contains a null value. In this case the object returned
    is either that parent, or the None object.

    {% pp_get_topic_hierarchy topic = object %}
       Do stuff with {{ pp_topic.hierarchy }}
    {% endpp_get_topic_hierarchy %}
    """

    context.push()
    namespace = get_namespace(context)

    root = kwargs.pop('topic', None)

    if root != None and isinstance(root, Topic):

        hierarchy = []
        hierarchy.insert(0, root)

        parent = root.parent

        while parent != None and parent.summary != '__NULL__':
            parent = root.parent
            hierarchy.insert(0, parent)
    else:
        hierarchy = None

    namespace['hierarchy'] = hierarchy
    output = nodelist.render(context)
    context.pop()

    return output


@block
def pp_get_topic_list(context, nodelist, *args, **kwargs):
    """
    This block tag will grab a list of topics. This also takes an argument 'topic'
    allowing the template to specify a root topic, in which case each child of this topic
    will be included in 'children'.

    In order to generate a url that will provide rng information to this tag via
    request.range, use a url tag of the following form:

    {% url pp-page template="filename.html" start=0 end=20 %}

    In this way, the tag can be invoked as follows:

    {% pp_get_topic_list range=request.range topic = root_topic %}
       Do stuff with {{ pp_topic.topic_list }}
    {% endpp_get_topic_list %}

    >>> from pirate_issues.models import Topic
    >>> topic = Topic(text = "newtopic")
    >>> topic.save()
    >>> topic2 = Topic(text = "childtopic", parent = topic)
    >>> topic2.save()
    >>> topic3 = Topic(text = "nexttopic", parent = topic2)
    >>> Topic.objects.all()
    [<Topic: taxes>, <Topic: debt>, <Topic: A test topic.>, <Topic: newtopic>, <Topic: childtopic>]
    >>> Topic.clean_objects.filter(parent = topic)
    [<Topic: childtopic>]
    >>> Topic.clean_objects.filter(parent = Topic.objects.null_dimension())
    []
    """

    context.push()
    namespace = get_namespace(context)
    root = kwargs.pop('topic', None)

    topic_list = []

    if root != None and isinstance(root, Topic):
        topic_list = Topic.objects.filter(parent=root).order_by('-children')
    else:
        topic_list = Topic.objects.filter(parent=Topic.objects.null_dimension()).order_by('-children')

    namespace['topic_list'] = topic_list
    namespace['count'] = topic_list.count()
    output = nodelist.render(context)
    context.pop()

    return output


@block
def oa_ingroup(context, nodelist, *args, **kwargs):
    context.push()
    namespace = get_namespace(context)

    obj = kwargs.get('object', None)
    user = kwargs.get('user', None)

    try:
        in_group = MyGroup.objects.get(topic=obj, user=user)
        namespace['in_group'] = True
    except:
        namespace['in_group'] = False

    output = nodelist.render(context)
    context.pop()

    return output


@block
def oa_mygroup_users(context, nodelist, *args, **kwargs):
    context.push()
    namespace = get_namespace(context)

    obj = kwargs.get('object', None)

    mygroups = MyGroup.objects.filter(topic=obj)

    namespace['groups'] = mygroups
    namespace['count'] = mygroups.count()

    output = nodelist.render(context)
    context.pop()

    return output


@block
def oa_get_group_settings(context, nodelist, *args, **kwargs):
    context.push()
    namespace = get_namespace(context)

    obj = kwargs.get('object', None)

    s, is_new = GroupSettings.objects.get_or_create(topic=obj)

    namespace['settings'] = s

    output = nodelist.render(context)
    context.pop()

    return output


@block
def pp_mygroups(context, nodelist, *args, **kwargs):
    context.push()
    namespace = get_namespace(context)

    user = kwargs.get('user', None)

    mygroups = MyGroup.objects.filter(user=user)

    namespace['mygroups'] = mygroups

    output = nodelist.render(context)
    context.pop()

    return output


_slugify_strip_re = re.compile(r'[^\w\s-]')
_slugify_hyphenate_re = re.compile(r'[-\s]+')
def _slugify(value):
    """
    Normalizes string, converts to lowercase, removes non-alpha characters,
    and converts spaces to hyphens.

    From Django's "django/template/defaultfilters.py".
    """
    import unicodedata
    if not isinstance(value, unicode):
        value = unicode(value)
    value = unicodedata.normalize('NFKD', value).encode('ascii', 'ignore')
    value = unicode(_slugify_strip_re.sub('', value).strip().lower())
    return _slugify_hyphenate_re.sub('-', value)


@block
def pp_getcreate_setting(context, nodelist, *args, **kwargs):
    context.push()
    namespace = get_namespace(context)

    topic = kwargs.get('topic', None)

    settings, is_new = GroupSettings.objects.get_or_create(topic=topic)

    namespace['settings'] = settings

    output = nodelist.render(context)
    context.pop()

    return output


@block
def pp_topic_form(context, nodelist, *args, **kwargs):
    '''
    This block tag can create or process forms eitfrom genericview.views import HttpRedirectException, namespace_gether to create or to modify arguments.
    Usage is as follows:

    {% pp_topic_form POST=request.POST path=request.path topic=pp_topic.topic root=some_topic %}
       Do stuff with {{ pp_topic.form }}.
    {% endpp_topic_form %}
    '''
    context.push()
    namespace = get_namespace(context)

    POST = kwargs.get('POST', None)
    topic = kwargs.get('topic', None)
    root = kwargs.get('root', Topic.objects.null_dimension())
    user = kwargs.get('user', None)

    if POST and POST.get("form_id") == "pp_topic_form" and user is not None:
        form = TopicForm(POST) if topic is None else TopicForm(POST, instance=topic)
        if form.is_valid():
            new_topic = form.save(commit=False)
            new_topic.is_featured = False
            new_topic.slug = _slugify(new_topic.summary)
            if root and isinstance(root, Topic):
                new_topic.parent = root
                new_topic.save()
            else:
                new_topic.parent = Topic.objects.null_dimension()
                new_topic.save()
            #raise HttpRedirectException(HttpResponseRedirect("/topics.html"))
            namespace['complete'] = True
            namespace['object_pk'] = new_topic.pk
            ctype = ContentType.objects.get_for_model(new_topic)
            namespace['content_type'] = ctype.pk
            #create Facilitator permissions for group creator
            perm_group, is_new = PermissionsGroup.objects.get_or_create(name="Facilitator", description="Permission group for Facilitation of Online Working Groups")
            perm = Permission(user=user, name='facilitator-permission', content_type=ctype,
                        object_pk=new_topic.pk, permissions_group=perm_group, component_membership_required=True)
            perm.save()
            mg = MyGroup(topic=new_topic, user=user)
            mg.save()
        else:
            namespace['errors'] = form.errors
    else:
        form = TopicForm() if topic is None else TopicForm(instance=topic)

    namespace['form'] = form
    output = nodelist.render(context)
    context.pop()

    return output


@block
def pp_setting_form(context, nodelist, *args, **kwargs):
    '''
    This block tag can create or process forms eitfrom genericview.views import HttpRedirectException, namespace_gether to create or to modify arguments.
    Usage is as follows:

    {% pp_topic_form POST=request.POST path=request.path topic=pp_topic.topic root=some_topic %}
       Do stuff with {{ pp_topic.form }}.
    {% endpp_topic_form %}
    '''
    context.push()
    namespace = get_namespace(context)

    POST = kwargs.get('POST', None)
    setting = kwargs.get('object', None)

    if POST and POST.get("form_id") == "oa_group_settings_form":
        form = SettingsForm(POST) if setting is None else SettingsForm(POST, instance=setting)
        form.save()
    else:
        form = SettingsForm() if setting is None else SettingsForm(instance=setting)

    namespace['form'] = form
    output = nodelist.render(context)
    context.pop()

    return output


class InviteForm(forms.ModelForm):

    def save(self, commit=True):
        newo = super(SettingsForm, self).save(commit=commit)
        return newo

    class Meta:
        model = GroupSettings
        exclude = ('topic')

    form_id = forms.CharField(widget=forms.HiddenInput(), initial="oa_group_settings_form")


class SettingsForm(forms.ModelForm):

    def save(self, commit=True):
        newo = super(SettingsForm, self).save(commit=commit)
        return newo

    class Meta:
        model = GroupSettings
        exclude = ('topic')

    form_id = forms.CharField(widget=forms.HiddenInput(), initial="oa_group_settings_form")


class TopicForm(forms.ModelForm):

    def save(self, commit=True):
        newo = super(TopicForm, self).save(commit=commit)
        return newo

    class Meta:
        model = Topic
        exclude = ('parent', 'children', 'is_featured', 'slug', 'group_members')

    form_id = forms.CharField(widget=forms.HiddenInput(), initial="pp_topic_form")
    summary = forms.CharField( max_length=100,
              widget=forms.TextInput(
                attrs={'size':'50', 'class':'inputText'}),label="Name of the Group")
    more_info = forms.CharField(required=False, max_length=100,
              widget=forms.TextInput(
                attrs={'size':'50', 'class':'inputText'}),label="Link to Group Website") 
    description = forms.CharField(widget=MarkItUpWidget(),label="Group Description")
    location = forms.CharField(label="Location", max_length=100,
              widget=forms.TextInput(
                attrs={'size': '50', 'class': 'inputText'}),required=False)
    form_id = forms.CharField(widget=forms.HiddenInput(), initial="pp_topic_form")