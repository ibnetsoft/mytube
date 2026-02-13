import database as db
import json

def test():
    projects = db.get_all_projects()
    if not projects:
        print("No projects found")
        return
    
    p_id = projects[0]['id']
    project = db.get_project(p_id)
    print(f"Project ID: {p_id}")
    print(f"Project Type: {type(project)}")
    print(f"Project Keys: {list(project.keys()) if project else 'None'}")
    print(f"Project Name: {project.get('name') if project else 'None'}")
    print(f"Full Project: {json.dumps(project, default=str)}")

if __name__ == "__main__":
    test()
