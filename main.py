# main.py
from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel
import requests
import random
import os
from dotenv import load_dotenv

from sqlalchemy.orm import Session
from db import SessionLocal, engine, Base
from models import Group, GroupMember

from deap import base, creator, tools

load_dotenv()
app = FastAPI(title="Group Microservice")

# Crear las tablas en la BD de PostgreSQL (si no existen)
Base.metadata.create_all(bind=engine)

# URL del microservicio de cursos (ajusta según tu configuración)
COURSE_MS_URL = os.getenv("COURSE_MS_URL")

# Matriz de compatibilidad de eneatipos (1 = compatible, 0 = no compatible)
matriz_compatibilidad_eneatipos = [
    [0, 1, 0, 1, 1, 1, 1, 0, 0],
    [1, 1, 1, 1, 1, 0, 1, 1, 0],
    [0, 1, 1, 0, 1, 0, 1, 0, 1],
    [1, 1, 0, 1, 0, 0, 0, 1, 0],
    [1, 1, 1, 0, 1, 1, 1, 0, 0],
    [1, 0, 0, 0, 1, 0, 1, 0, 1],
    [1, 1, 1, 0, 1, 1, 1, 1, 0],
    [0, 1, 0, 1, 0, 0, 1, 0, 1],
    [0, 0, 1, 0, 0, 1, 0, 1, 1],
]


# Modelo Pydantic para la solicitud de creación de grupos
class CreateGroupsRequest(BaseModel):
    course_id: str
    number_of_groups: int
    
class CreateGroupsSpecializedRequest(BaseModel):
    course_id: str
    number_of_groups: int
    students: list[dict]

# Modelo Pydantic para la respuesta de cada grupo
class GroupResponse(BaseModel):
    group_number: int
    course_id: str
    student_ids: list[str]
    


# Dependencia para obtener la sesión de BD
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.post("/groups/create-random", response_model=list[GroupResponse])
def create_groups_random(request: CreateGroupsRequest, db: Session = Depends(get_db)):
    # 1. Obtener estudiantes desde el microservicio de cursos
    try:
        # Se asume que el endpoint del microservicio de cursos es:
        # GET /courses/{course_id}/students, que retorna una lista de IDs o de objetos con id
        response = requests.get(f"http://localhost:3000/api/courses/{request.course_id}/students")
        response.raise_for_status()
        students = response.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al obtener estudiantes: {str(e)}")

    if not students:
        raise HTTPException(status_code=404, detail="No se encontraron estudiantes para este curso")

    # Extraer IDs en caso de que se reciban objetos
    if isinstance(students[0], dict):
        student_ids = [student["id"] for student in students]
    else:
        student_ids = students

    # 2. Validar el número de grupos
    num_groups = request.number_of_groups
    if num_groups <= 0:
        raise HTTPException(status_code=400, detail="El número de grupos debe ser mayor que cero.")

    # 3. Eliminar los grupos existentes para este curso (y sus miembros)
    existing_groups = db.query(Group).filter(Group.course_id == request.course_id).all()
    if existing_groups:
        for group in existing_groups:
            # Debido a que la relación está definida con cascade="all, delete-orphan",
            # al eliminar el grupo, también se eliminarán sus miembros.
            db.delete(group)
        db.commit()

    # 4. Mezclar aleatoriamente la lista de estudiantes
    random.shuffle(student_ids)

    # 5. Distribuir los estudiantes en grupos (algoritmo round-robin)
    groups_list = [[] for _ in range(num_groups)]
    for index, student_id in enumerate(student_ids):
        groups_list[index % num_groups].append(student_id)

    # print(groups_list)
    # 6. Crear y guardar los nuevos grupos y sus miembros en la base de datos
    result = []
    for i, group_students in enumerate(groups_list, start=1):
        db_group = Group(course_id=request.course_id, group_number=i)
        db.add(db_group)
        db.commit()
        db.refresh(db_group)

        # Crear registros para cada miembro del grupo
        for student_id in group_students:
            db_member = GroupMember(group_id=db_group.id, student_id=student_id)
            db.add(db_member)
        db.commit()

        result.append(GroupResponse(
            group_number=i,
            course_id=request.course_id,
            student_ids=group_students
        ))

    return result

# Endpoint para crear grupos especializados
@app.post("/groups/create-specialized", response_model=list[GroupResponse])
def create_groups_specialized(request: CreateGroupsSpecializedRequest, db: Session = Depends(get_db)):
    estudiantes = request.students
    n_grupos = request.number_of_groups
    
    n_estudiantes = len(estudiantes)
    print(n_estudiantes)
    # Crear tipo de fitness, maximizando una función de adecuación
    creator.create("FitnessMax", base.Fitness, weights=(1.0,))
    # Crear tipo de individuo como una lista de grupos
    creator.create("Individual", list, fitness=creator.FitnessMax)
    
    def crear_individuo():
        """Crear un individuo como una lista de grupos, manejando casos en los que el número de estudiantes no es divisible por el número de grupos."""
        estudiantes_aleatorios = random.sample(estudiantes, len(estudiantes))  # Mezclar los estudiantes

        # Calcular cuántos estudiantes deben ir a cada grupo
        tamaño_base = n_estudiantes // n_grupos  # Tamaño mínimo de cada grupo
        sobrante = n_estudiantes % n_grupos  # Cantidad de grupos que tendrán un estudiante adicional

        grupos = []
        start_idx = 0
        for i in range(n_grupos):
            # Si hay sobrante, los primeros grupos tendrán un estudiante más
            tamaño_grupo = tamaño_base + 1 if i < sobrante else tamaño_base
            grupos.append(estudiantes_aleatorios[start_idx:start_idx + tamaño_grupo])
            start_idx += tamaño_grupo

        return grupos

    def evaluar_individuo(individuo):
        """Función de evaluación del individuo."""

        compatibilidad_eneatipo = 0
        preferencias = 0
        penalizacion_no_favoritos = 0
        favorito_de = 0
        no_favorito_de = 0

        for grupo in individuo:
            ids_grupo = [est['id'] for est in grupo]


            # Evaluar compatibilidad de eneatipos usando la matriz
            for i in range(len(grupo)):
                for j in range(i + 1, len(grupo)):
                    eneatipo1 = grupo[i]['eneatipo'] - 1  # Restamos 1 para indexar correctamente
                    eneatipo2 = grupo[j]['eneatipo'] - 1
                    if eneatipo1 >= 0 and eneatipo2 >= 0:  # No evaluar eneatipos '0'
                        compatibilidad_eneatipo += matriz_compatibilidad_eneatipos[eneatipo1][eneatipo2]

            # Evaluar compañeros favoritos y no favoritos
            for est in grupo:
                # Premiar si el estudiante está con sus favoritos
                preferencias += sum(1 for favorito in est['favoritos'] if favorito in ids_grupo)
                # Penalizar si el estudiante está con sus no favoritos
                penalizacion_no_favoritos += sum(1 for no_favorito in est['no_favoritos'] if no_favorito in ids_grupo)

                # Evaluar si es favorito o no favorito de otros en el grupo
                for compañero in grupo:
                    if est['id'] in compañero['favoritos']:
                        favorito_de += 1  # Premiar si alguien en el grupo lo elige como favorito
                        if est['id'] in est['favoritos']:  # Premiar aún más si es mutuo
                            favorito_de += 1
                    if est['id'] in compañero['no_favoritos']:
                        no_favorito_de += 1  # Penalizar si alguien lo elige como no favorito

        # Fitness: premiamos la compatibilidad, las preferencias, y las relaciones mutuas de favorito
        # Penalizamos desequilibrio de sexos, no favoritos y relaciones mutuas de no favorito

        fitness = (preferencias * 2 + compatibilidad_eneatipo + favorito_de - penalizacion_no_favoritos - no_favorito_de)
        return (fitness,)

    def cruzar_grupos(ind1, ind2):
        """Cruce de dos individuos asegurando que no haya duplicados en los grupos."""
        # Combinar los grupos de ambos padres
        todos_estudiantes = sum(ind1, []) + sum(ind2, [])
        random.shuffle(todos_estudiantes)
        # Volver a crear grupos sin solapamiento, manejando la división desigual
        tamaño_base = n_estudiantes // n_grupos
        sobrante = n_estudiantes % n_grupos
        nuevo_individuo = []
        start_idx = 0
        for i in range(n_grupos):
            tamaño_grupo = tamaño_base + 1 if i < sobrante else tamaño_base
            nuevo_individuo.append(todos_estudiantes[start_idx:start_idx + tamaño_grupo])
            start_idx += tamaño_grupo
        return creator.Individual(nuevo_individuo),

    def mutar_grupos(ind):
        """Mutación que intercambia estudiantes entre grupos, asegurando que no se dupliquen."""
        todos_estudiantes = sum(ind, [])
        random.shuffle(todos_estudiantes)
        # Volver a crear grupos sin solapamiento, manejando la división desigual
        tamaño_base = n_estudiantes // n_grupos
        sobrante = n_estudiantes % n_grupos
        nuevo_individuo = []
        start_idx = 0
        for i in range(n_grupos):
            tamaño_grupo = tamaño_base + 1 if i < sobrante else tamaño_base
            nuevo_individuo.append(todos_estudiantes[start_idx:start_idx + tamaño_grupo])
            start_idx += tamaño_grupo
        ind[:] = nuevo_individuo
        return ind,
    
    toolbox = base.Toolbox()
    toolbox.register("individual", tools.initIterate, creator.Individual, crear_individuo)
    toolbox.register("population", tools.initRepeat, list, toolbox.individual)

    # Registro de operadores
    toolbox.register("evaluate", evaluar_individuo)
    toolbox.register("mate", cruzar_grupos)
    toolbox.register("mutate", mutar_grupos)
    toolbox.register("select", tools.selTournament, tournsize=3)
    
    # Crear población inicial de 50 individuos
    population = toolbox.population(n=50)
    
    # Probabilidad de cruzamiento y mutación
    CXPB, MUTPB, NGEN = 0.5, 0.15, 40
    
    # Evaluar la población inicial
    fitnesses = list(map(toolbox.evaluate, population))
    for ind, fit in zip(population, fitnesses):
        ind.fitness.values = fit

    # Ciclo de generaciones
    for gen in range(NGEN):
        # Selección de padres
        offspring = toolbox.select(population, len(population))
        offspring = list(map(toolbox.clone, offspring))

        # Aplicar cruzamiento a la población
        for child1, child2 in zip(offspring[::2], offspring[1::2]):
            if random.random() < CXPB:
                toolbox.mate(child1, child2)
                del child1.fitness.values
                del child2.fitness.values

        # Aplicar mutación
        for mutant in offspring:
            if random.random() < MUTPB:
                toolbox.mutate(mutant)
                del mutant.fitness.values

        # Evaluar los individuos con fitness no válidos
        invalid_ind = [ind for ind in offspring if not ind.fitness.valid]
        fitnesses = list(map(toolbox.evaluate, invalid_ind))
        for ind, fit in zip(invalid_ind, fitnesses):
            ind.fitness.values = fit

        # Reemplazar la población actual por los descendientes
        population[:] = offspring

    # Obtener el mejor individuo de la población
    best_ind = tools.selBest(population, 1)[0]
    print("Mejor individuo (grupos):", [[e['id'] for e in grupo] for grupo in best_ind])
    print("Adecuación del mejor individuo:", best_ind.fitness.values)
    groups_list = []
    for grupo in best_ind:
        groups_list.append([est['id'] for est in grupo])
    print(groups_list)

    # Eliminar los grupos existentes para este curso (y sus miembros)
    existing_groups = db.query(Group).filter(Group.course_id == request.course_id).all()
    if existing_groups:
        for group in existing_groups:
            # Debido a que la relación está definida con cascade="all, delete-orphan",
            # al eliminar el grupo, también se eliminarán sus miembros.
            db.delete(group)
        db.commit()

    # Crear y guardar los nuevos grupos y sus miembros en la base de datos
    result = []
    for i, group_students in enumerate(groups_list, start=1):
        db_group = Group(course_id=request.course_id, group_number=i)
        db.add(db_group)
        db.commit()
        db.refresh(db_group)

        # Crear registros para cada miembro del grupo
        for student_id in group_students:
            db_member = GroupMember(group_id=db_group.id, student_id=student_id)
            db.add(db_member)
        db.commit()

        result.append(GroupResponse(
            group_number=i,
            course_id=request.course_id,
            student_ids=group_students
        ))
    return result


# Endpoint para obtener todos los grupos de un curso
@app.get("/groups/course/{course_id}", response_model=list[GroupResponse])
def get_groups_by_course(course_id: str, db: Session = Depends(get_db)):
    groups = db.query(Group).filter(Group.course_id == course_id).all()
    if not groups:
        raise HTTPException(status_code=404, detail="No se encontraron grupos para este curso")

    result = []
    for group in groups:
        student_ids = [member.student_id for member in group.members]
        result.append(GroupResponse(
            group_number=group.group_number,
            course_id=group.course_id,
            student_ids=student_ids
        ))
    return result

# Endpoint para obtener el/los grupo(s) al que pertenece un alumno
@app.get("/groups/student/{student_id}", response_model=list[GroupResponse])
def get_groups_by_student(student_id: str, db: Session = Depends(get_db)):
    group_members = db.query(GroupMember).filter(GroupMember.student_id == student_id).all()
    if not group_members:
        raise HTTPException(status_code=404, detail="El estudiante no pertenece a ningún grupo")

    result = []
    for member in group_members:
        group = db.query(Group).filter(Group.id == member.group_id).first()
        if group:
            student_ids = [m.student_id for m in group.members]
            result.append(GroupResponse(
                group_number=group.group_number,
                course_id=group.course_id,
                student_ids=student_ids
            ))
    return result

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=3003, reload=True)
