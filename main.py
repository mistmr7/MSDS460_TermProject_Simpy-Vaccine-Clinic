import numpy as np
import pandas as pd

# import queue
# from functools import partial, wraps
import simpy
from loguru import logger

RUSHED_PCT = 25
MEAN_VACCINE_TIME = 3
MEAN_CHECK_IN_TIME = 1
NUM_NURSES = 1
NUM_RECEPTIONISTS = 2
REPRODUCIBLE = True
SIM_HRS = 2
SIM_SECS = SIM_HRS * 3600

patient_info_df = pd.DataFrame(
    columns=["patient_id", "patient_type", "balk_max", "renege_max", "check_in_time"]
)


class VaccineClinic(object):
    def __init__(self, env, num_receptionists, num_nurses):
        self.env = env
        self.receptionist = simpy.PriorityResource(env, num_receptionists)
        self.nurse = simpy.Resource(env, num_nurses)
        self.check_in_queue = []
        self.vaccination_queue = []
        self.balkers = []
        self.renegers = []
        self.patient_info_df = pd.DataFrame(
            columns=["patient_id", "patient_type", "balk_max", "renege_max"]
        )

    def check_in(self, patient_id):
        # Create a normal distribution with a mean of 1 and a SD of 0.5
        # and return the absolute value of that as the check in time.
        with self.receptionist.request() as req:
            yield req
            print(patient_id)
            renege_time = self.patient_info_df.loc[
                self.patient_info_df["patient_id"] == patient_id
            ]["renege_max"].values[0]
            checked_in_time = self.patient_info_df.loc[
                self.patient_info_df["patient_id"] == patient_id
            ]["check_in_time"].values[0]
            check_in_line_time = (
                np.abs(np.random.normal(MEAN_CHECK_IN_TIME, 0.5, 1)[0]) * 60
            )
            if (self.env.now - checked_in_time) > renege_time:
                self.check_in_queue.remove(patient_id)
                self.renegers.append(patient_id)
                print(
                    f"{patient_id} removed from the check in queue after"
                    + f" {self.env.now - checked_in_time} seconds in the check in "
                    f"queue at time {self.env.now + check_in_line_time}."
                )
            else:
                print(
                    f"{patient_id} checked in to the vaccination queue after"
                    + f" {check_in_line_time} seconds in the check in "
                    f"queue at time {self.env.now + check_in_line_time}. The total wait "
                    + f"time was {self.env.now + check_in_line_time - checked_in_time}"
                )
                self.check_in_queue.remove(patient_id)
                self.vaccination_queue.append(patient_id)
                yield self.env.timeout(check_in_line_time)
                self.env.process(self.vaccinate(patient_id))

    def vaccinate(self, patient_id):
        # Create a normal distribution with a mean of 2 and a SD of 1
        # and return the absolute value of that as the vaccination time.
        with self.nurse.request() as req:
            yield req
            vaccination_time = np.abs(np.random.normal(MEAN_VACCINE_TIME, 1, 1)[0]) * 60
            print(
                f"{patient_id} checked in to the vaccination queue after"
                + f" {vaccination_time} seconds in the check in "
                f"queue at time {self.env.now + vaccination_time}."
            )
            self.vaccination_queue.remove(patient_id)
            yield self.env.timeout(vaccination_time)

    def arrive(self):
        patient_id = 0
        while True:
            time_between_arrivals = np.abs(np.random.normal(0.5, 0.25, 1)[0]) * 60
            yield self.env.timeout(time_between_arrivals)
            patient_id += 1
            patient = self.randomize_patient_type(patient_id)
            balking_queue_length = patient.loc[patient["patient_id"] == patient_id][
                "balk_max"
            ].values[0]
            time = self.env.now
            yield self.env.timeout(0)
            if balking_queue_length > len(self.check_in_queue):
                print(
                    f"{patient_id} added to check-in queue at time {time}. "
                    + f"The queue length is {len(self.check_in_queue)}"
                )
                self.check_in_queue.append(patient_id)
                self.env.process(self.check_in(patient_id))
            else:
                print(f"{patient_id} has balked at the check in line at time {time}")
                self.balkers.append(patient_id)

    def randomize_patient_type(self, patient_id):
        if np.random.binomial(1, RUSHED_PCT / 100) == 1:
            patient_type = "rushed"
            balk_max = 5
            renege_max = 1 * MEAN_CHECK_IN_TIME * 60
        # If a person is relaxed, they will wait in a line of 15 or less
        # people and will wait in line for 15 times the mean vaccination
        # time
        else:
            patient_type = "relaxed"
            balk_max = 15
            renege_max = 1 * MEAN_VACCINE_TIME * 60
        new_patient = pd.DataFrame(
            {
                "patient_id": [patient_id],
                "patient_type": [patient_type],
                "balk_max": [balk_max],
                "renege_max": [renege_max],
                "check_in_time": [self.env.now],
            }
        )
        self.patient_info_df = pd.concat([self.patient_info_df, new_patient])
        return pd.concat([self.patient_info_df, new_patient])


if REPRODUCIBLE:
    np.random.seed(1111)
env = simpy.Environment()
clinic = VaccineClinic(env, NUM_RECEPTIONISTS, NUM_NURSES)
env.process(clinic.arrive())
env.run(until=SIM_SECS)
print(clinic.balkers)
print(clinic.renegers)
