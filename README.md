# Vaccination Clinic Simulation

## Overview

This project presents a discrete event simulation (DES) model using SimPy to optimize a vaccination clinic handling both walk-in and scheduled appointments. The goal is to maximize patient vaccinations while minimizing employee idle time, which affects staffing costs.

## Objective

Determine the optimal number of receptionists and nurses for high vaccination rates and low employee idle time by analyzing key metrics such as wait times, service times, vaccination throughput, and staff free time over 100 simulation runs.

## Key Features

### Arrival Streams

- **Appointments**: Fixed intervals with scheduled patients arriving every 15 minutes.
- **Walk-ins**: Normally distributed arrival times, with high flow rates during peak times (before work, after work, and during lunch) and low flow rates during other times.

### Resources

- **Receptionists**: Varying from 1 to 10.
- **Nurses**: Varying from 1 to 10.

### Processes

- **Check-in with Receptionist**: Patients arrive and join a check-in queue to meet with a receptionist.
- **Balk at Check-in Queue**: Rushed patients will balk (leave without entering the queue) if the queue has five or more patients. Relaxed patients will balk if the queue has 15 or more patients.
- **Renege in Check-in Queue**: Rushed patients will renege (leave without being vaccinated) if their total time in the clinic exceeds five times the mean check-in plus vaccination time. Relaxed patients will renege if their time exceeds fifteen times the mean check-in plus vaccination time.
- **Renege in Vaccination Queue**: Patients may also renege while waiting in the vaccination queue under the same conditions as for the check-in queue.
- **Get Vaccine from Nurse**: After checking in, patients join a vaccination queue to be vaccinated by a nurse.

### Parameters

- **Simulation Time**: 12 hours.
- **Mean Check-in Time**: 1 minute.
- **Mean Vaccine Time**: 3 minutes.
- **Patient Types**: Patients are categorized as "relaxed" or "rushed" using binomial randomization, with 25% classified as rushed.

## Results

- Optimal configuration: 2 receptionists and 5 nurses
- 93.91% vaccination rate
- 55.49 patient balks
- 16.32 reneges
- 31,336 seconds of receptionist idle time
- 32,810 seconds of nurse idle time
