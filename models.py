# models.py
from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship
from db import Base

class Group(Base):
    __tablename__ = "groups"

    id = Column(Integer, primary_key=True, index=True)
    course_id = Column(String, index=True)  # Vincula el grupo al curso
    group_number = Column(Integer)

    # Relación: un grupo tiene muchos miembros
    members = relationship("GroupMember", back_populates="group", cascade="all, delete-orphan")

class GroupMember(Base):
    __tablename__ = "group_members"

    id = Column(Integer, primary_key=True, index=True)
    group_id = Column(Integer, ForeignKey("groups.id"))
    student_id = Column(String, index=True)

    group = relationship("Group", back_populates="members")
