from django import template

from pirate_core import namespace_get
from oa_cache.views import render_hashed

from settings import DOMAIN

from customtags.decorators import block_decorator
register = template.Library()
block = block_decorator(register)

get_namespace = namespace_get('pp_cache')


@block
def pp_get_cached_data(context, nodelist, *args, **kwargs):
    """
    This templatetag is called only when the page is initially loaded, to
    give the template access to 

    :param object: id of django.db.models.Model object
    :type object: str 
    :param user: djngo.contrib.auth.models.User object
    :returns:
        * pp_consensus.consensus
            This is the consensus object itself
        * pp_consensus.interest
            Holds the interest integer generated by the ranking algorithm
        * pp_consensus.controversy
            Holds the controversy rating generated by the controversy ranking algorithm
        * pp_consensus.consensus
            This is the consensus object itself
        * pp_consensus.votes
            Number of votes on this object
    :requires user:
        * pp_consensus.user_updown
            Returns user voting information if parameter is present
        * pp_consensus.user_rating
            Returns user voting information if parameter is present

    An example HTML template:

    .. code-block:: html
        :linenos:

        {% pp_consensus_get object=object user=request.user %}
                
                {{pp_consensus.interest}}
                
                {{pp_consensus.consensus}}

                <p> Object has {{pp_consensus.votes}} votes </p>
        {% endpp_consensus_get %}

    """
    context.push()
    namespace = get_namespace(context)

    request = kwargs.get('request', None)

    if request.META['PATH_INFO'][0:3] == '/p/':
        renderdict = render_hashed(request, None, None, extracontext={'TYPE': 'HTML'})

        namespace['key'] = request.META['PATH_INFO'].replace('/', '')
        namespace['rendertype'] = renderdict['rendertype']
        namespace['data'] = renderdict['renders']
        namespace['DOMAIN'] = DOMAIN
        namespace['object'] = renderdict['object']
        namespace['rendered_list'] = None

        namespace['nojs'] = True
    output = nodelist.render(context)
    context.pop()

    return output
