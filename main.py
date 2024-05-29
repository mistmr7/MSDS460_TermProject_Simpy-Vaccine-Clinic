import numpy as np
import pandas as pd
import sys

# import queue
# from functools import partial, wraps
import simpy
from loguru import logger
from icecream import ic


class VaccineClinic(object):
    def __init__(self, env, num_receptionists, num_nurses, SIM_SECS):
        self.env = env
        self.num_receptionists = num_receptionists
        self.num_nurses = num_nurses
        self.receptionist = simpy.PriorityResource(env, num_receptionists)
        self.nurse = simpy.Resource(env, num_nurses)
        self.check_in_queue = []
        self.vaccination_queue = []
        self.balkers = []
        self.renegers = []
        self.patient_info_df = pd.DataFrame(
            columns=[
                "patient_id",
                "patient_type",
                "balk_max",
                "renege_max",
                "check_in_time",
                "leave_time",
                "action",
            ]
        )
        self.event_log_df = pd.DataFrame(columns=["patient_id", "action", "time"])
        self.vaccination_queue_length = []
        self.check_in_queue_length = []
        self.SIM_SECS = SIM_SECS
        self.nurse_wasted_time = []
        self.receptionist_wasted_time = []

    def print_stats(self, resource, time1, time2):
        if resource == self.nurse:
            self.nurse_wasted_time.append(
                (resource.capacity - resource.count) * (time2 - time1)
            )
        else:
            self.receptionist_wasted_time.append(
                (resource.capacity - resource.count) * (time2 - time1)
            )

    def check_in(self, patient_id, patient_priority, time):
        # Create a normal distribution with a mean of 1 and a SD of 0.5
        # and return the absolute value of that as the check in time.
        time2 = self.env.now
        ic(time2 - time)
        self.print_stats(self.receptionist, time, time2)
        with self.receptionist.request(priority=patient_priority) as req:
            yield req

            check_in_line_time = (
                np.abs(np.random.normal(MEAN_CHECK_IN_TIME, 0.5, 1)[0]) * 60
            )
            renege_time, checked_in_time = self.grab_renege_and_check_in_times(
                patient_id
            )
            if (self.env.now - checked_in_time) > renege_time:
                self.check_in_queue.remove(patient_id)
                self.renegers.append(patient_id)
                logger.trace(
                    f"{patient_id} removed from the check in queue after"
                    + f" {self.env.now - checked_in_time} seconds in the check in "
                    f"queue at time {self.env.now + check_in_line_time}."
                )
                self.add_to_event_log(
                    "Reneged From Check-In Queue", patient_id, self.env.now
                )
            else:
                logger.trace(
                    f"{patient_id} checked in to the vaccination queue after"
                    + f" {check_in_line_time} seconds in the check in "
                    f"queue at time {self.env.now + check_in_line_time}. The total wait "
                    + f"time was {self.env.now + check_in_line_time - checked_in_time}"
                )
                self.check_in_queue.remove(patient_id)
                self.vaccination_queue.append(patient_id)
                yield self.env.timeout(check_in_line_time)
                self.add_to_event_log(
                    "Switch to Vaccination Queue", patient_id, self.env.now
                )
                self.env.process(self.vaccinate(patient_id, time))

    def grab_renege_and_check_in_times(self, patient_id):
        renege_time = self.patient_info_df.loc[
            self.patient_info_df["patient_id"] == patient_id
        ]["renege_max"].values[0]
        checked_in_time = self.patient_info_df.loc[
            self.patient_info_df["patient_id"] == patient_id
        ]["check_in_time"].values[0]
        return renege_time, checked_in_time

    def add_to_event_log(self, action, patient_id, time):
        event_log_row = pd.DataFrame(
            {"patient_id": [patient_id], "action": [action], "time": [time]}
        )
        self.event_log_df = pd.concat([self.event_log_df, event_log_row])

    def vaccinate(self, patient_id, time):
        # Create a normal distribution with a mean of 2 and a SD of 1
        # and return the absolute value of that as the vaccination time.
        time2 = self.env.now
        self.print_stats(self.nurse, time, time2)
        with self.nurse.request() as req:
            yield req
            vaccination_time = np.abs(np.random.normal(MEAN_VACCINE_TIME, 1, 1)[0]) * 60
            renege_time, checked_in_time = self.grab_renege_and_check_in_times(
                patient_id
            )
            logger.trace(
                f"{patient_id} removed from the check in queue after"
                + f" {self.env.now - checked_in_time} combined seconds in "
                "the check in queue and vaccination queue "
                f"at time {self.env.now + vaccination_time}."
            )
            if (self.env.now - checked_in_time) > renege_time:
                self.vaccination_queue.remove(patient_id)
                self.renegers.append(patient_id)
                logger.trace(
                    f"{patient_id} removed from the check in queue after"
                    + f" {self.env.now - checked_in_time} combined seconds in "
                    "the check in queue and vaccination queue "
                    f"at time {self.env.now + vaccination_time}."
                )
                self.vaccination_queue_length.append(
                    [self.env.now, len(self.vaccination_queue)]
                )
                self.add_to_event_log(
                    "Reneged From Vaccination Queue", patient_id, self.env.now
                )
                self.patient_info_df.loc[
                    self.patient_info_df["patient_id"] == patient_id, "action"
                ] = "Reneged"
                self.patient_info_df.loc[
                    self.patient_info_df["patient_id"] == patient_id, "leave_time"
                ] = self.env.now
            else:
                logger.trace(
                    f"{patient_id} checked in to the vaccination queue after"
                    + f" {vaccination_time} seconds in the check in "
                    f"queue at time {self.env.now + vaccination_time}. The "
                    f"vaccination queue length is {(len(self.vaccination_queue))}."
                )
                self.vaccination_queue.remove(patient_id)
                self.vaccination_queue_length.append(
                    [self.env.now, len(self.vaccination_queue)]
                )
                yield self.env.timeout(vaccination_time)
                self.add_to_event_log("Vaccinated", patient_id, self.env.now)
                self.patient_info_df.loc[
                    self.patient_info_df["patient_id"] == patient_id, "action"
                ] = "Vaccinated"
                self.patient_info_df.loc[
                    self.patient_info_df["patient_id"] == patient_id, "leave_time"
                ] = self.env.now

    def arrive(self):
        patient_id = 0
        while True:
            time_to_send = self.env.now
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
                self.add_to_event_log("Join Check-in Queue", patient_id, time)
                logger.trace(
                    f"{patient_id} added to check-in queue at time {time}. "
                    + f"The queue length is {len(self.check_in_queue)}"
                )
                self.check_in_queue.append(patient_id)
                self.env.process(
                    self.check_in(patient_id, patient_priority=0, time=time_to_send)
                )
            else:
                self.add_to_event_log("balk", patient_id, time)
                logger.trace(
                    f"{patient_id} has balked at the check in line at time {time}"
                )
                self.balkers.append(patient_id)
                self.patient_info_df.loc[
                    self.patient_info_df["patient_id"] == patient_id, "action"
                ] = "Balked"
                self.patient_info_df.loc[
                    self.patient_info_df["patient_id"] == patient_id, "leave_time"
                ] = self.env.now
            self.check_in_queue_length.append([time, len(self.check_in_queue)])
            if self.env.now >= SIM_SECS:
                return False

    def scheduled_arrivals(self):
        patient_id = "A_0"
        while True:
            yield self.env.timeout(APPOINTMENT_FREQ)
            prefix, suffix = patient_id.split("_")
            patient_id = f"{prefix}_{int(suffix) + 1}"
            time = self.env.now
            scheduled_patient = pd.DataFrame(
                {
                    "patient_id": [patient_id],
                    "patient_type": ["Scheduled"],
                    "balk_max": [20],
                    "renege_max": [1800],
                    "check_in_time": [time],
                    "leave_time": [0],
                    "action": [0],
                }
            )
            self.patient_info_df = pd.concat([self.patient_info_df, scheduled_patient])
            yield self.env.timeout(0)
            self.add_to_event_log("Join Check-in Queue", patient_id, time)
            logger.trace(
                f"{patient_id} added to front of check-in queue at time {time}. "
                + f"The queue length is {len(self.check_in_queue)}"
            )
            self.check_in_queue.insert(0, patient_id)
            self.env.process(self.check_in(patient_id, patient_priority=-1, time=time))
            self.check_in_queue_length.append([time, len(self.check_in_queue)])
            if self.env.now >= SIM_SECS:
                return False

    def randomize_patient_type(self, patient_id):
        if np.random.binomial(1, RUSHED_PCT / 100) == 1:
            patient_type = "rushed"
            balk_max = 5
            renege_max = 5 * (MEAN_CHECK_IN_TIME + MEAN_VACCINE_TIME) * 60
        # If a person is relaxed, they will wait in a line of 15 or less
        # people and will wait in line for 15 times the mean vaccination
        # time
        else:
            patient_type = "relaxed"
            balk_max = 15
            renege_max = 15 * (MEAN_CHECK_IN_TIME + MEAN_VACCINE_TIME) * 60
        new_patient = pd.DataFrame(
            {
                "patient_id": [patient_id],
                "patient_type": [patient_type],
                "balk_max": [balk_max],
                "renege_max": [renege_max],
                "check_in_time": [self.env.now],
                "leave_time": [0],
                "action": [0],
            }
        )
        self.patient_info_df = pd.concat([self.patient_info_df, new_patient])
        return pd.concat([self.patient_info_df, new_patient])


RUSHED_PCT = 25
MEAN_VACCINE_TIME = 3
MEAN_CHECK_IN_TIME = 1
APPOINTMENT_FREQ = 15 * 60  # Appts every 15 mins
NUM_NURSES = 5
NUM_RECEPTIONISTS = 2
REPRODUCIBLE = True
SIM_HRS = 1
SIM_SECS = SIM_HRS * 60 * 60
logger.add(sys.stderr, format="{message}", level="TRACE")
logger.add(
    f"Vaccine_Clinic_{SIM_HRS} Hrs -{NUM_RECEPTIONISTS} Recpts-{NUM_NURSES} Nurses-{int(APPOINTMENT_FREQ/60)} min Appts.log",
    level="TRACE",
    format="{message}",
)
if REPRODUCIBLE:
    np.random.seed(1112)
env = simpy.Environment()
clinic = VaccineClinic(env, NUM_RECEPTIONISTS, NUM_NURSES, SIM_SECS)
env.process(clinic.scheduled_arrivals())
env.process(clinic.arrive())
env.run()
clinic.event_log_df.to_excel(
    f"Vaccine_Clinic_Log-{NUM_RECEPTIONISTS}-{NUM_NURSES}-{int(APPOINTMENT_FREQ/60)}.xlsx",
    index=False,
)
vax_queue_df = pd.DataFrame(
    clinic.vaccination_queue_length, columns=["time", "vaccination_queue_length"]
)
vax_queue_df.to_excel("vaccination_queue_length.xlsx", index=False)
check_in_queue_df = pd.DataFrame(
    clinic.check_in_queue_length, columns=["time", "check_in_queue_length"]
)
check_in_queue_df.to_excel("check_in_queue_length.xlsx", index=False)
clinic.patient_info_df["service_time"] = (
    clinic.patient_info_df["leave_time"] - clinic.patient_info_df["check_in_time"]
)
clinic.patient_info_df.to_excel("patient_info_df.xlsx", index=False)
clinic.patient_info_df[clinic.patient_info_df["action"] == "Balked"].to_excel(
    "patient_balk_df.xlsx", index=False
)
clinic.patient_info_df[clinic.patient_info_df["action"] == "Reneged"].to_excel(
    "patient_renege_df.xlsx", index=False
)

nurse_wasted_df = pd.DataFrame(clinic.nurse_wasted_time, columns=["Nurse Free Time"])
nurse_wasted_df.to_excel("nurse_wasted_time.xlsx", index=False)


receptionist_wasted_df = pd.DataFrame(
    clinic.receptionist_wasted_time, columns=["Receptionist Free Time"]
)
receptionist_wasted_df.to_excel("Receptionist_wasted_time.xlsx", index=False)
