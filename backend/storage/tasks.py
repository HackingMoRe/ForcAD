import json
from typing import List, Optional

import aioredis
import redis

import helpers
import storage
from helpers import models
from storage import caching

_UPDATE_TEAMTASKS_STATUS_QUERY = f"""
UPDATE teamtasks SET status = %s, public_message = %s, private_message = %s, command = %s, 
up_rounds = up_rounds + %s
WHERE task_id = %s AND team_id = %s AND round = %s
"""

_INITIALIZE_TEAMTASKS_FROM_PREVIOUS_QUERY = """
WITH prev_table AS (
    SELECT score, stolen, lost, up_rounds FROM teamtasks 
    WHERE task_id = %(task_id)s AND team_id = %(team_id)s AND round = %(round)s - 1
)
INSERT INTO TeamTasks (task_id, team_id, round, score, stolen, lost, up_rounds) 
SELECT %(task_id)s, %(team_id)s, %(round)s, score, stolen, lost, up_rounds 
FROM prev_table
"""


def get_tasks() -> List[models.Task]:
    """Get list of tasks registered in database"""
    with storage.get_redis_storage().pipeline(transaction=True) as pipeline:
        while True:
            try:
                pipeline.watch('tasks:cached')
                cached = pipeline.exists('tasks:cached')
                if not cached:
                    caching.cache_tasks()

                break
            except redis.WatchError:
                continue

        # pipeline is not in multi mode now
        tasks = pipeline.smembers('tasks')
        tasks = list(models.Task.from_json(task) for task in tasks)

    return tasks


async def get_tasks_async(loop) -> List[models.Task]:
    """Get list of tasks registered in the database (asynchronous version)"""

    redis_aio = await storage.get_async_redis_pool(loop)

    while True:
        try:
            await redis_aio.watch('tasks:cached')

            cached = await redis_aio.exists('tasks:cached')
            if not cached:
                # TODO: make it asynchronous?
                caching.cache_tasks()

            await redis_aio.unwatch()
        except aioredis.WatchVariableError:
            continue
        else:
            break

    tasks = await redis_aio.smembers('tasks')
    tasks = list(models.Task.from_json(task) for task in tasks)

    return tasks


def update_task_status(task_id: int, team_id: int, round: int, checker_verdict: helpers.models.CheckerActionResult):
    """ Update task status in database

        :param task_id: task id
        :param team_id: team id
        :param round: round to update table for
        :param checker_verdict: instance of CheckerActionResult
    """
    add = 0
    if checker_verdict.status == helpers.status.TaskStatus.UP:
        add = 1

    conn = storage.get_db_pool().getconn()
    curs = conn.cursor()
    curs.execute(
        _UPDATE_TEAMTASKS_STATUS_QUERY,
        (
            checker_verdict.status.value,
            checker_verdict.public_message,
            checker_verdict.private_message,
            json.dumps(checker_verdict.command),
            add,
            task_id,
            team_id,
            round,
        )
    )

    conn.commit()
    curs.close()
    storage.get_db_pool().putconn(conn)


def get_teamtasks(round: int) -> Optional[List[dict]]:
    """Fetch team tasks for current specified round

        :param round: current round
        :return: dictionary of team tasks or None
    """
    with storage.get_redis_storage().pipeline(transaction=True) as pipeline:
        pipeline.get(f'teamtasks:{round}:cached')
        pipeline.get(f'teamtasks:{round}')
        cached, result = pipeline.execute()

    if not cached:
        return None

    teamtasks = json.loads(result.decode())
    return teamtasks


def filter_teamtasks_for_participants(teamtasks: List[dict]) -> List[dict]:
    """Remove private message and rename public message
    to "message" for a list of teamtasks, remove 'command'
    """
    result = []

    for obj in teamtasks:
        obj['message'] = obj['public_message']
        obj.pop('private_message')
        obj.pop('public_message')
        obj.pop('command')
        result.append(obj)

    return result


def get_teamtasks_for_participants(round: int) -> Optional[List[dict]]:
    """Fetch team tasks for current specified round, with private message removed

        :param round: current round
        :return: dictionary of team tasks or None
    """
    teamtasks = get_teamtasks(round=round)
    return filter_teamtasks_for_participants(teamtasks)


def get_teamtasks_of_team(team_id: int, current_round: int) -> Optional[List[dict]]:
    """Fetch teamtasks history for a team, cache if necessary"""
    with storage.get_redis_storage().pipeline(transaction=True) as pipeline:
        while True:
            try:
                pipeline.watch(f'teamtasks:team:{team_id}:round:{current_round}:cached')

                cached = pipeline.exists(f'teamtasks:team:{team_id}:round:{current_round}:cached')
                if not cached:
                    caching.cache_teamtasks_for_team(team_id=team_id, current_round=current_round)

                result = pipeline.get(f'teamtasks:team:{team_id}:round:{current_round}')

                break
            except redis.WatchError:
                continue

    try:
        result = result.decode()
        teamtasks = json.loads(result)
    except (UnicodeDecodeError, AttributeError, json.decoder.JSONDecodeError):
        teamtasks = None

    return teamtasks


def get_teamtasks_of_team_for_participants(team_id: int, current_round: int) -> Optional[List[dict]]:
    """Fetch teamtasks history for a team, cache if necessary, with private message stripped"""
    return filter_teamtasks_for_participants(
        get_teamtasks_of_team(
            team_id=team_id,
            current_round=current_round,
        )
    )


def initialize_teamtasks(round: int):
    """Add blank entries to "teamtasks" table for a new round

        :param round: round to create entries for
    """

    teams = storage.teams.get_teams()
    tasks = storage.tasks.get_tasks()

    conn = storage.get_db_pool().getconn()
    curs = conn.cursor()

    for team in teams:
        for task in tasks:
            curs.execute(
                _INITIALIZE_TEAMTASKS_FROM_PREVIOUS_QUERY,
                {
                    'task_id': task.id,
                    'team_id': team.id,
                    'round': round,
                },
            )

    conn.commit()
    curs.close()
    storage.get_db_pool().putconn(conn)
