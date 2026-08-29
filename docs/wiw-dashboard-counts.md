# WIW dashboard counts

The mobile administration dashboard intentionally shows the combined number of available OpenShifts from live When I Work plus native A+ Solution shifts.

To avoid double-counting imported WIW shifts that also exist in the local database, the dashboard adds only local OpenShift slots whose shift has no `wiw_shift_id` to the live WIW count.

Therefore `OpenShifts verfügbar` represents:

`live WIW OpenShift instances + native A+ OpenShift slots`

The Dienstplan can contain imported WIW rows as well as native A+ rows; the dashboard total must not be reduced to the native-only local count.
