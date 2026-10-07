from .schemas import CampaignPlan, ResearchResult

NAMES = ['Atlas Robotics','Nordic Automation','Fieldwork Labs','Vector Machines','Kinetic Systems','Aster Robotics','Orbit Autonomy','Helix Robotics','Lumen Machines','Terra Automation']

def plan(query, count):
    return CampaignPlan(title='European robotics startups', target_count=count, geography='Europe', ideal_customer='Robotics teams developing autonomous systems', qualification_criteria=['Autonomous robots', 'Simulation testing relevance'], search_queries=['European robotics startups autonomous robots simulation'])


def candidates(count):
    return [{'company_name': NAMES[i % 10] + (f' {i // 10 + 1}' if i >= 10 else ''), 'url': f'https://robotics-{i+1:02d}.example'} for i in range(count)]


def page(lead):
    return {'title': lead['company_name'], 'url': 'https://' + lead['domain'], 'content': f'{lead["company_name"]} is a European robotics company. Our autonomous robots adapt to changing production environments. We build industrial mobile robots and use simulation to test navigation and deployment scenarios. This is a synthetic demo source, not a live website.'}


def research(lead, source):
    number = int(lead['domain'].split('-')[1].split('.')[0])
    score = 65 + (number * 7) % 35
    eligible = score >= 70
    return ResearchResult.model_validate({'lead_id': str(lead['id']), 'enrichment': {'industry': 'Industrial robotics','summary': 'Autonomous robots for changing production environments.','product':'Industrial mobile robots','geography':'Europe','signals':['Autonomy','Simulation testing']}, 'qualification':{'score':score,'verdict':'strong_fit' if score >= 85 else 'possible_fit' if eligible else 'not_a_fit','reasons':['Autonomous navigation and simulation testing align with the requested customer profile.'], 'evidence':[{'source_id':str(source['id']),'quote':'Our autonomous robots adapt to changing production environments.','claim':'Develops adaptive autonomous robots'}]}, 'draft': {'subject':f'Simulation testing for {lead["company_name"]}', 'body': f'Hi {lead["company_name"]} team,\n\nYour work on autonomous robots caught my attention. We help robotics teams test changing production scenarios in simulation before deployment.\n\nWould a short conversation be useful?'} if eligible else None})
