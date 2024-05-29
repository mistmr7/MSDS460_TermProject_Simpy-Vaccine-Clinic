import numpy as np
import pandas as pd
import sys

# import queue
# from functools import partial, wraps
import simpy
from loguru import logger
from icecream import ic


class VaccineClinic(object):
    # Initialize the clinic with the environment and number of employees
    def __init__(self, env, num_receptionists, num_nurses):
        self.env = env
        self.num_receptionists = num_receptionists
        self.num_nurses = num_nurses
        # Set a receptionist as a priority resource
        self.receptionist = simpy.PriorityResource(env, num_receptionists)
        # Set a nurse as a resource
        self.nurse = simpy.Resource(env, num_nurses)
        # Set the queues
        self.check_in_queue = []
        self.vaccination_queue = []
        # Start a list of balkers and renegers
        self.balkers = []
        self.renegers = []
        # Initialize a DataFrame for full patient info
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
        # Initialize a DataFrame for events in the clinic
        self.event_log_df = pd.DataFrame(columns=["patient_id", "action", "time"])
        # Start a list of queue lengths throughout the simulation
        self.vaccination_queue_length = []
        self.check_in_queue_length = []
        # Start lists of inactive employees
        self.nurse_wasted_time = []
        self.receptionist_wasted_time = []

    def log_wasted_resource_time(self, resource, time1, time2):
        # Log the amount of time nurses and receptionists are not
        # Interacting with a patient
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
        self.log_wasted_resource_time(self.receptionist, time, time2)
        # If a receptionist is available, start them off with a check-in
        # patient. Otherwise, wait for a receptionist to be available.
        # A scheduled patient will get priority and be put at the front of the line
        with self.receptionist.request(priority=patient_priority) as req:
            yield req
            # Set a random amount of time taken to check in with the
            # receptionist with a SD of 1 and a mean set in the program settings
            check_in_line_time = (
                np.abs(np.random.normal(MEAN_CHECK_IN_TIME, 0.5, 1)[0]) * 60
            )
            # Grab the amount of seconds needed to pass for this patient to renege
            # and the initial time at which they checked in.
            renege_time, checked_in_time = self.grab_renege_and_check_in_times(
                patient_id
            )
            # Check to see if the length of time passed since arrival is greater
            # than the renege time
            if (self.env.now - checked_in_time) > renege_time:
                # If time passed is greater than renege time, remove the patient
                # from the check in queue and append the patient to the renegers
                # list
                self.check_in_queue.remove(patient_id)
                self.renegers.append(patient_id)
                logger.trace(
                    f"{patient_id} removed from the check in queue after"
                    + f" {self.env.now - checked_in_time} seconds in the check in "
                    f"queue at time {self.env.now}."
                )
                # Add the patient to the event log as Reneged
                self.add_to_event_log(
                    "Reneged From Check-In Queue", patient_id, self.env.now
                )
                # Add Reneged and leave time to patient info df
                self.patient_info_df.loc[
                    self.patient_info_df["patient_id"] == patient_id, "action"
                ] = "Reneged"
                self.patient_info_df.loc[
                    self.patient_info_df["patient_id"] == patient_id, "leave_time"
                ] = self.env.now
            else:
                # If time passed has not surpassed the renege time
                # After check in with receptionist time has passed
                # continue with the simulation
                yield self.env.timeout(check_in_line_time)
                # log time speaking with receptionist and check in queue time
                logger.trace(
                    f"{patient_id} checked in to the vaccination queue after"
                    + f" {check_in_line_time} seconds in the check in "
                    f"queue at time {self.env.now}. The check-in queue wait "
                    + f"time was {self.env.now - checked_in_time}"
                )
                # Remove the patient from the check in queue
                self.check_in_queue.remove(patient_id)
                # Add the patient to the vaccination queue
                self.vaccination_queue.append(patient_id)
                # Add move to vaccination queue to event log
                self.add_to_event_log(
                    "Switch to Vaccination Queue", patient_id, self.env.now
                )
                # Start the vaccination simulation
                self.env.process(self.vaccinate(patient_id, time))

    def grab_renege_and_check_in_times(self, patient_id):
        # Check the amount of time a patient will stay in line
        # And the time they checked into the check in line
        renege_time = self.patient_info_df.loc[
            self.patient_info_df["patient_id"] == patient_id
        ]["renege_max"].values[0]
        checked_in_time = self.patient_info_df.loc[
            self.patient_info_df["patient_id"] == patient_id
        ]["check_in_time"].values[0]
        return renege_time, checked_in_time

    def add_to_event_log(self, action, patient_id, time):
        # Add patient_id, action, and a timestamp to the event log
        event_log_row = pd.DataFrame(
            {"patient_id": [patient_id], "action": [action], "time": [time]}
        )
        self.event_log_df = pd.concat([self.event_log_df, event_log_row])

    def vaccinate(self, patient_id, time):
        # Create a normal distribution with a mean of 2 and a SD of 1
        # and return the absolute value of that as the vaccination time.
        time2 = self.env.now
        # Check for nurses who are free and log the time they've been free
        self.log_wasted_resource_time(self.nurse, time, time2)
        # When a nurse is free, set them up with a patient
        with self.nurse.request() as req:
            yield req
            # Randomize a vaccination time with MEAN_VACCINE_TIME setting and 1 minute
            # standard deviation
            vaccination_time = np.abs(np.random.normal(MEAN_VACCINE_TIME, 1, 1)[0]) * 60
            # Grab the amount of seconds needed to pass for this patient to renege
            # and the initial time at which they checked in.
            renege_time, checked_in_time = self.grab_renege_and_check_in_times(
                patient_id
            )
            # If more time has passed than the renege amount
            if (self.env.now - checked_in_time) > renege_time:
                # Remove the patient from the vaccination queue
                self.vaccination_queue.remove(patient_id)
                # Append the patient to the renegers list
                self.renegers.append(patient_id)
                # Log the time reneged from the vaccination queue
                # And time spent in line total
                logger.trace(
                    f"{patient_id} reneged from vaccination queue after"
                    + f" {self.env.now - checked_in_time} combined seconds in "
                    "the check in queue and vaccination queue "
                    f"at time {self.env.now}."
                )
                # Log vaccination queue length after removing patient
                self.vaccination_queue_length.append(
                    [self.env.now, len(self.vaccination_queue)]
                )
                # Add reneging from Vaccination Queue to the event log
                self.add_to_event_log(
                    "Reneged From Vaccination Queue", patient_id, self.env.now
                )
                # Add reneging as an action to the patient dataframe
                self.patient_info_df.loc[
                    self.patient_info_df["patient_id"] == patient_id, "action"
                ] = "Reneged"
                # Add leave time to patient dataframe
                self.patient_info_df.loc[
                    self.patient_info_df["patient_id"] == patient_id, "leave_time"
                ] = self.env.now
            else:
                # If patient has not made it to their renege time
                # Wait vaccination time for vaccination to complete
                yield self.env.timeout(vaccination_time)
                # Remove the patient from the vaccination queue
                self.vaccination_queue.remove(patient_id)
                # Log the time vaccination completed
                logger.trace(
                    f"{patient_id} spent {vaccination_time} with the nurse "
                    + f"at time {self.env.now}. The vaccination"
                    f" queue length is {(len(self.vaccination_queue))}."
                )
                # Log the vaccination queue length after removing the patient
                self.vaccination_queue_length.append(
                    [self.env.now, len(self.vaccination_queue)]
                )
                # Add vaccination to the event log
                self.add_to_event_log("Vaccinated", patient_id, self.env.now)
                # Log that the patient was vaccinated successfully in the patient df
                self.patient_info_df.loc[
                    self.patient_info_df["patient_id"] == patient_id, "action"
                ] = "Vaccinated"
                # Log time vaccinated
                self.patient_info_df.loc[
                    self.patient_info_df["patient_id"] == patient_id, "leave_time"
                ] = self.env.now

    def arrive(self):
        # Function set for walk-in arrivals

        # Initialize patient ID
        patient_id = 0
        # Start infinite loop to open vaccine clinic for walk-ins
        while True:
            time_to_send = self.env.now
            # Set the average time between arrivals to 30 seconds with 15 seconds
            # standard deviation and randomize
            time_between_arrivals = np.abs(np.random.normal(0.5, 0.25, 1)[0]) * 60
            # Wait until someone arrives to continue
            yield self.env.timeout(time_between_arrivals)
            # Add patient ID
            patient_id += 1
            # Randomize the patient type between 'Rushed' and 'Relaxed'
            patient = self.randomize_patient_type(patient_id)
            # Check for the length of check-in queue line that will make the
            # patient leave without entering the queue
            balking_queue_length = patient.loc[patient["patient_id"] == patient_id][
                "balk_max"
            ].values[0]
            # set the time added to the check in queue
            time = self.env.now
            yield self.env.timeout(0)
            # If the check in queue is shorter than the balk length
            if balking_queue_length > len(self.check_in_queue):
                # Add the patient to the event log as joining check in queue
                self.add_to_event_log("Join Check-in Queue", patient_id, time)
                # Log patient joining check in queue
                logger.trace(
                    f"{patient_id} added to check-in queue at time {time}. "
                    + f"The queue length is {len(self.check_in_queue)}"
                )
                # Add patient to the check in queue
                self.check_in_queue.append(patient_id)
                # Start the check in process with a normal priority
                self.env.process(
                    self.check_in(patient_id, patient_priority=0, time=time_to_send)
                )
            else:
                # If the check in queue is too long
                # Add patient to the event log as balking
                self.add_to_event_log("balk", patient_id, time)
                # Log the balk
                logger.trace(
                    f"{patient_id} has balked at the check in line at time {time}"
                )
                # Add the patient to the list of balkers
                self.balkers.append(patient_id)
                # Set the action as balked in the patient dataframe
                self.patient_info_df.loc[
                    self.patient_info_df["patient_id"] == patient_id, "action"
                ] = "Balked"
                # Set the time balked in the patient dataframe
                self.patient_info_df.loc[
                    self.patient_info_df["patient_id"] == patient_id, "leave_time"
                ] = self.env.now
            # Add the length of the check in queue to the check in queue length list
            self.check_in_queue_length.append([time, len(self.check_in_queue)])
            # If closing time has occurred, stop allowing walk ins
            if self.env.now >= SIM_SECS:
                return False

    def scheduled_arrivals(self):
        # Function set for appointments

        # Initialize the patient ID with a Prefix of A for Appt
        patient_id = "A_0"
        # Start allowing appointments to happen
        while True:
            # Add a patient with an appointment based on the appointment
            # Frequency set in the program settings
            yield self.env.timeout(APPOINTMENT_FREQ)
            # Add 1 to patient ID to keep it unique
            prefix, suffix = patient_id.split("_")
            patient_id = f"{prefix}_{int(suffix) + 1}"
            # Set the time of arrival
            time = self.env.now
            # Create a row for the scheduled patient
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
            # Add the row to the patient info dataframe
            self.patient_info_df = pd.concat([self.patient_info_df, scheduled_patient])
            yield self.env.timeout(0)
            # Add check in queue join to the event log
            self.add_to_event_log("Join Check-in Queue", patient_id, time)
            # Log patient going to front of check in queue line
            logger.trace(
                f"{patient_id} added to front of check-in queue at time {time}. "
                + f"The queue length is {len(self.check_in_queue)}"
            )
            # Insert the patient into the number 1 spot in the check in queue
            self.check_in_queue.insert(0, patient_id)
            # Initialize the check in process for the patient with a priority
            # That sets them next in line
            self.env.process(self.check_in(patient_id, patient_priority=-1, time=time))
            # Check the length of the check in queue and append it to the list
            self.check_in_queue_length.append([time, len(self.check_in_queue)])
            # If closing time, allow no more scheduled patients
            if self.env.now >= SIM_SECS:
                return False

    def randomize_patient_type(self, patient_id):
        # If a person is rushed, they will wait in a line of 5 or less
        # people and will wait in line for 5 times the mean vaccination
        # time plus mean check in time
        if np.random.binomial(1, RUSHED_PCT / 100) == 1:
            patient_type = "rushed"
            balk_max = 5
            renege_max = 5 * (MEAN_CHECK_IN_TIME + MEAN_VACCINE_TIME) * 60
        # If a person is relaxed, they will wait in a line of 15 or less
        # people and will wait in line for 15 times the mean vaccination
        # time plus mean check in time
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


RUSHED_PCT = 25  # Set percent of rushed patients
MEAN_VACCINE_TIME = 3
MEAN_CHECK_IN_TIME = 1
APPOINTMENT_FREQ = 15 * 60  # Appts every 15 mins
NUM_NURSES = 5
NUM_RECEPTIONISTS = 2
REPRODUCIBLE = True  # Use same random seeding if reproducible is true
SIM_HRS = 12
SIM_SECS = SIM_HRS * 60 * 60
# Set up the logging
logger.add(sys.stderr, format="{message}", level="TRACE")
logger.add(
    f"Vaccine_Clinic_{SIM_HRS} Hrs -{NUM_RECEPTIONISTS} Recpts-{NUM_NURSES} Nurses-{int(APPOINTMENT_FREQ/60)} min Appts.log",
    level="TRACE",
    format="{message}",
)
# Set the random seed if reproducible set to true
if REPRODUCIBLE:
    np.random.seed(1112)
# Initialize the environment
env = simpy.Environment()
# Initialize the clinic
clinic = VaccineClinic(env, NUM_RECEPTIONISTS, NUM_NURSES)
# Start the scheduled arrivals process for the environment
env.process(clinic.scheduled_arrivals())
# Start the walk in arrivals process for the environment
env.process(clinic.arrive())
# Run the environment
env.run()
# create event log excel file
clinic.event_log_df.to_excel(
    f"Vaccine_Clinic_Log-{NUM_RECEPTIONISTS}-{NUM_NURSES}-{int(APPOINTMENT_FREQ/60)}.xlsx",
    index=False,
)
# Create Vax Queue length excel file
vax_queue_df = pd.DataFrame(
    clinic.vaccination_queue_length, columns=["time", "vaccination_queue_length"]
)
vax_queue_df.to_excel("vaccination_queue_length.xlsx", index=False)
# Create Check-In Queue length excel file
check_in_queue_df = pd.DataFrame(
    clinic.check_in_queue_length, columns=["time", "check_in_queue_length"]
)
check_in_queue_df.to_excel("check_in_queue_length.xlsx", index=False)
# Calculate the total time each patient spent at the clinic
clinic.patient_info_df["service_time"] = (
    clinic.patient_info_df["leave_time"] - clinic.patient_info_df["check_in_time"]
)
# Create excel file from patient info dataframe
clinic.patient_info_df.to_excel("patient_info_df.xlsx", index=False)
# Create balked patient dataframe from filtered patient info dataframe
clinic.patient_info_df[clinic.patient_info_df["action"] == "Balked"].to_excel(
    "patient_balk_df.xlsx", index=False
)
# Create reneged patient dataframe from filtered patient info dataframe
clinic.patient_info_df[clinic.patient_info_df["action"] == "Reneged"].to_excel(
    "patient_renege_df.xlsx", index=False
)
# Create a nurse wasted time excel file from available nurse times
nurse_wasted_df = pd.DataFrame(clinic.nurse_wasted_time, columns=["Nurse Free Time"])
nurse_wasted_df.to_excel("nurse_wasted_time.xlsx", index=False)
# Create a receptionist wasted time excel file from available receptionist times
receptionist_wasted_df = pd.DataFrame(
    clinic.receptionist_wasted_time, columns=["Receptionist Free Time"]
)
receptionist_wasted_df.to_excel("Receptionist_wasted_time.xlsx", index=False)
