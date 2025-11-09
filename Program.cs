double currentSpeed = train.TrainSpeedMph;
                    // Handle very small speeds (effectively stopped)
                    if (Math.Abs(currentSpeed) <= 0.01)
                    {
                        currentSpeed = 0.0;  // Explicitly set to zero
                        train.Status = TrainStatus.Stopped;
                    }
                    double lastKnownSpeed = lastSpeed.ContainsKey(id) ? lastSpeed[id] : currentSpeed;
                    lastSpeed[id] = currentSpeed;

                    // Log speed changes
                    if (Math.Abs(currentSpeed - lastKnownSpeed) > 0.1)  // Only log significant changes
                    {
                        string status = currentSpeed == 0.0 ? "stopped" : 
                                      currentSpeed > lastKnownSpeed ? "accelerating" : "decelerating";
                        string msg = $"[{simNow:T}] {train.EngineerName} on {train.TrainSymbol} {status} " +
                                   $"(Speed: {currentSpeed:F1} MPH, Change: {(currentSpeed - lastKnownSpeed):F1} MPH)";
                        Logger.LogDebug(msg);
                        if (discordEnabled && (currentSpeed == 0.0 || Math.Abs(currentSpeed - lastKnownSpeed) > 5.0))
                        {
                            await discordClient.SendMessage(msg);
                        }
                    }